"""Escalation signals carry no model opinion, and the judge validates its verdict."""

from types import SimpleNamespace

import pytest

from dosimeter.config.settings import Bounds, Settings
from dosimeter.errors import BudgetError, ExternalServiceError
from dosimeter.evaluation.judge import JudgeVerdict, Verdict, judge_claim
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.escalation import (
    EscalationOutcome,
    FiredTrigger,
    Trigger,
    TriggerSignals,
    evaluate,
)


def settings_for_tests() -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
    )


def test_the_signal_model_has_no_self_reported_confidence() -> None:
    fields = set(TriggerSignals.model_fields)

    assert not {name for name in fields if "confidence" in name and "floor" not in name}
    assert "fields_below_floor" in fields


def test_all_eleven_triggers_have_names() -> None:
    assert len(list(Trigger)) == 11
    assert Trigger.PLANNED_SPECIAL_EXPOSURE_VALID.value == "planned_special_exposure_valid"


def test_an_outcome_names_every_fired_trigger() -> None:
    outcome = EscalationOutcome(
        evaluated=list(Trigger),
        fired=[
            FiredTrigger(trigger=Trigger.AT_OR_ABOVE_ANNUAL_LIMIT, detail="tede 6.2 rem"),
            FiredTrigger(trigger=Trigger.NOTIFICATION_REQUIRED),
        ],
    )

    assert outcome.escalates
    assert outcome.names() == ["dose_at_or_above_annual_limit", "notification_required"]
    assert "notification_required" in outcome.reason()


def test_the_stand_in_evaluator_fires_nothing() -> None:
    assert not evaluate(TriggerSignals()).escalates


class FakeJudgeModel:
    """Stands in for get_chat_model(): with_structured_output(...).invoke(...)."""

    def __init__(self, parsed: JudgeVerdict | None) -> None:
        self.parsed = parsed

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        self.messages = messages
        raw = SimpleNamespace(usage_metadata={"input_tokens": 120, "output_tokens": 30})
        return {
            "raw": raw,
            "parsed": self.parsed,
            "parsing_error": None if self.parsed else "no tool call",
        }


def test_the_judge_returns_a_validated_verdict() -> None:
    model = FakeJudgeModel(JudgeVerdict(verdict=Verdict.SUPPORTED, reason="states the 5 rem limit"))

    judged = judge_claim(
        "The annual limit is 5 rem TEDE.",
        "CFR-20-LIMITS#0004",
        "text",
        settings_for_tests(),
        model=model,
    )

    assert judged.verdict is Verdict.SUPPORTED
    assert judged.input_tokens == 120
    assert judged.model_id == "text-model-id"


def test_a_verdict_that_does_not_validate_is_a_typed_failure() -> None:
    with pytest.raises(ExternalServiceError):
        judge_claim("claim", "cited", "text", settings_for_tests(), model=FakeJudgeModel(None))


class FakeRecorder:
    """Keeps what RunRecorder would have written for the judge."""

    def __init__(self) -> None:
        self.model_calls: list[dict] = []

    def model_called(self, **call) -> None:
        self.model_calls.append(call)


def test_the_judge_counts_and_records_its_own_call() -> None:
    ledger = SessionLedger(bounds=Bounds())
    recorder = FakeRecorder()
    model = FakeJudgeModel(JudgeVerdict(verdict=Verdict.SUPPORTED, reason="states the limit"))

    judge_claim(
        "claim",
        "cited",
        "text",
        settings_for_tests(),
        model=model,
        ledger=ledger,
        recorder=recorder,
        agent="reviewer",
    )

    assert ledger.session_tokens == 150
    assert recorder.model_calls[0]["agent"] == "reviewer"
    assert recorder.model_calls[0]["role"] == "judge"
    assert recorder.model_calls[0]["input_tokens"] == 120


def test_the_judge_does_not_start_once_the_budget_is_spent() -> None:
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=10), session_input_tokens=10)
    model = FakeJudgeModel(JudgeVerdict(verdict=Verdict.SUPPORTED))

    with pytest.raises(BudgetError):
        judge_claim(
            "claim",
            "cited",
            "text",
            settings_for_tests(),
            model=model,
            ledger=ledger,
            agent="reviewer",
        )

    assert not hasattr(model, "messages")
