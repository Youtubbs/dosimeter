"""Escalation signals carry no model opinion, and the judge validates its verdict."""

from __future__ import annotations

import pytest


from dosimeter.config.settings import Settings
from dosimeter.errors import ExternalServiceError
from dosimeter.evaluation.judge import GroundednessJudge, Verdict
from dosimeter.harness.escalation import (
    EscalationOutcome,
    FiredTrigger,
    Trigger,
    TriggerSignals,
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


def converse_returning(text: str):
    def converse(**kwargs):
        converse.seen = kwargs
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "usage": {"inputTokens": 120, "outputTokens": 30},
        }

    return converse


def test_the_judge_returns_a_validated_verdict() -> None:
    converse = converse_returning(
        '{"verdict": "supported", "reason": "the chunk states the 5 rem limit"}'
    )
    judge = GroundednessJudge(settings=settings_for_tests(), converse=converse)

    judged = judge.judge("The annual limit is 5 rem TEDE.", "CFR-20-LIMITS#0004", "text")

    assert judged.verdict is Verdict.SUPPORTED
    assert judged.input_tokens == 120
    assert judged.model_id == "text-model-id"




def test_a_verdict_that_is_not_json_is_a_typed_failure() -> None:
    judge = GroundednessJudge(settings=settings_for_tests(), converse=converse_returning("no idea"))

    with pytest.raises(ExternalServiceError):
        judge.judge("claim", "chunk", "text")



