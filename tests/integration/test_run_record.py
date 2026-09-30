"""The run record writer, the eligibility check and what trace renders."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from dosimeter.config.settings import Bounds, Settings
from dosimeter.graph.schemas import DispatchPlan, ReviewerVerdict, WorkerProposal
from dosimeter.harness.assess import run_assess
from dosimeter.harness.eligibility import record_eligibility
from dosimeter.harness.escalation import EscalationOutcome, FiredTrigger, Trigger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.harness.trace import render_trace
from dosimeter.logging_config import correlation_scope
from dosimeter.repository import Session, orm, queries, seeds

EXPOSURE = "EXP-2026-0412"
OFFICER = "OFF-101"


def settings_for_tests(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
        **overrides,
    )


class FakeChatModel:
    """Stands in for get_chat_model(): with_structured_output(...).invoke(...), with token usage."""

    def __init__(self, plan: DispatchPlan, input_tokens: int, output_tokens: int) -> None:
        self.plan = plan
        self.usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        raw = SimpleNamespace(usage_metadata=self.usage)
        return {"raw": raw, "parsed": self.plan, "parsing_error": None}


def coordinator_answers(
    monkeypatch: pytest.MonkeyPatch,
    plan: DispatchPlan,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """The real Coordinator node, with the model call answered by a stand-in."""

    monkeypatch.setattr(
        "dosimeter.graph.nodes.coordinator.get_chat_model",
        lambda **_: FakeChatModel(plan, input_tokens, output_tokens),
    )


@pytest.fixture
def seeded(db: Session) -> Session:
    seeds.apply_seeds(db)
    db.commit()
    return db


def recorder_for(db: Session, command: str = "assess") -> RunRecorder:
    officer = queries.officer_by_code(db, OFFICER)
    recorder = RunRecorder(
        session=db,
        exposure_id=EXPOSURE,
        officer_id=officer.id,
        command=command,
    )
    recorder.start()
    return recorder


def test_a_turn_writes_one_row_with_its_children(seeded: Session) -> None:
    with correlation_scope("corr-1"):
        recorder = recorder_for(seeded)

        recorder.dispatched("notification", "dose over an annual limit")
        recorder.dispatched("written_report", "a report may be owed")
        recorder.tool_called(
            "search_knowledge_base",
            {"query": "20.2202 thresholds"},
            {"chunks": 3},
            "ok",
            worker="notification",
            duration_ms=41.0,
        )
        recorder.rule_invoked(
            "R1",
            "not_required",
            {"tede_rem": 6.2},
            result={"threshold": "25 rem"},
            threshold_named="20.2202(a)(1)(i)",
            dose_quantity="total_effective_dose_equivalent",
            path="harness",
        )
        recorder.retrieved(
            "what does 20.2202 require",
            ["CFR-20-REPORTS#0007"],
            [0.81],
            ["in_force"],
            status_filter="in_force",
        )
        recorder.model_called("text-model-id", "reasoning", 900, 120, agent="notification")
        recorder.model_called("text-model-id", "reasoning", 400, 60, agent="written_report")
        recorder.reviewer_verdict(1, "written_report", "approved")
        recorder.guardrail_event("output", "allowed")
        recorder.finish("complete")

    stored = queries.get_run_record(seeded, recorder.run_id)
    detail = queries.run_record_detail(seeded, recorder.run_id)

    assert stored.correlation_id == "corr-1"
    assert stored.command == "assess"
    assert stored.outcome == "complete"
    assert stored.token_totals == {"notification": 1020, "written_report": 460}
    assert [item.worker for item in detail["dispatches"]] == ["notification", "written_report"]
    assert detail["tool_invocations"][0].arguments == {"query": "20.2202 thresholds"}
    assert detail["rule_invocations"][0].dose_quantity == "total_effective_dose_equivalent"
    assert detail["retrievals"][0].statuses == ["in_force"]
    assert detail["reviewer_verdicts"][0].verdict == "approved"


def test_nothing_on_a_run_record_carries_a_name_or_a_dose_history(seeded: Session) -> None:
    recorder = recorder_for(seeded)

    recorder.tool_called(
        "get_exposure_extraction",
        {"crew_note": "Worker Name: Marguerite Ostrander\nDose: 6.2 rem"},
        {"fields": [{"field": "Worker Name", "value": "Marguerite Ostrander"}]},
        "ok",
    )
    recorder.rule_invoked("R4", "valid", {"lifetime_dose": 6.0, "worker_id": "WKR-1047"})
    recorder.finish("complete")

    detail = queries.run_record_detail(seeded, recorder.run_id)
    tool = detail["tool_invocations"][0]
    rule = detail["rule_invocations"][0]

    assert "Marguerite Ostrander" not in str(tool.arguments)
    assert "Marguerite Ostrander" not in str(tool.result)
    assert rule.inputs["lifetime_dose"] == "[redacted]"
    assert rule.inputs["worker_id"] == "WKR-1047"


def test_a_correction_is_a_new_row_pointing_at_the_original(seeded: Session) -> None:
    recorder = recorder_for(seeded)
    recorder.finish("notification_required")

    correction_id = recorder.correct("not_required")

    original = queries.get_run_record(seeded, recorder.run_id)
    correction = queries.get_run_record(seeded, correction_id)

    assert original.outcome == "notification_required"
    assert correction.corrects_run_id == recorder.run_id
    assert seeded.scalar(select(func.count()).select_from(orm.RunRecordRow)) == 2


def fired(*triggers: Trigger) -> EscalationOutcome:
    return EscalationOutcome(
        evaluated=list(Trigger),
        fired=[FiredTrigger(trigger=item, detail="") for item in triggers],
    )


def test_a_fired_trigger_queues_the_dossier_naming_every_trigger(seeded: Session) -> None:
    recorder = recorder_for(seeded)

    result = record_eligibility(
        session=seeded,
        exposure_id=EXPOSURE,
        district="District 2",
        outcome=fired(Trigger.NOTIFICATION_REQUIRED, Trigger.AT_OR_ABOVE_ANNUAL_LIMIT),
        recorder=recorder,
    )

    queued = queries.list_review_queue(seeded, ["District 2"])

    assert result.escalated
    assert len(queued) == 1
    assert "notification_required" in queued[0].reason
    assert "dose_at_or_above_annual_limit" in queued[0].reason


def dispatch_two_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan two workers and approve on the first review."""

    coordinator_answers(
        monkeypatch,
        DispatchPlan(
            workers=["notification", "written_report"],
            goals={"notification": "does any tier fire", "written_report": "is a report owed"},
            rationale="a dose over an annual limit",
        ),
        input_tokens=300,
        output_tokens=50,
    )

    def worker(name):
        def run(state):
            return {
                "proposals": {name: WorkerProposal(worker=name, kind=name)},
                "usage": {"input_tokens": 100},
            }

        return run

    def reviewer(state):
        return {
            "reviewer_verdicts": [
                ReviewerVerdict(iteration=1, worker="written_report", verdict="approved")
            ],
            "reviewer_iterations": state.get("reviewer_iterations", 0) + 1,
        }

    monkeypatch.setattr("dosimeter.graph.graph.notification_node", worker("notification"))
    monkeypatch.setattr("dosimeter.graph.graph.written_report_node", worker("written_report"))
    monkeypatch.setattr("dosimeter.graph.graph.make_reviewer_node", lambda **_: reviewer)
    monkeypatch.setattr(
        "dosimeter.graph.nodes.eligibility.evaluate",
        lambda signals: fired(Trigger.AT_OR_ABOVE_ANNUAL_LIMIT),
    )


def test_assess_runs_the_graph_and_persists_the_dossier_and_record(
    seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dosimeter.graph.checkpointer import setup_checkpointer
    from tests.integration.test_checkpointer import database_settings

    setup_checkpointer(database_settings())
    dispatch_two_workers(monkeypatch)

    result = run_assess(
        session=seeded,
        exposure_id=EXPOSURE,
        officer_code=OFFICER,
        settings=settings_for_tests(),
    )

    dossier = queries.latest_dossier(seeded, EXPOSURE)
    detail = queries.run_record_detail(seeded, result.run_id)

    assert result.outcome == "escalated"
    assert result.escalated
    assert dossier.payload["workers"] == ["notification", "written_report"]
    assert dossier.payload["escalation_signals"] == ["dose_at_or_above_annual_limit"]
    assert {item.worker for item in detail["dispatches"]} == {"notification", "written_report"}
    assert detail["reviewer_verdicts"][0].verdict == "approved"
    assert result.duration_seconds < 30

    # the Coordinator's dispatches, its model call and the per-agent totals are on the record
    dispatches = {item.worker: item for item in detail["dispatches"]}
    assert dispatches["notification"].reason == "does any tier fire"
    assert dispatches["notification"].iteration == 1
    assert dispatches["notification"].redispatch_trigger is None
    assert [
        (call.agent, call.role, call.input_tokens, call.output_tokens)
        for call in detail["model_calls"]
    ] == [("coordinator", "reasoning", 300, 50)]
    assert queries.get_run_record(seeded, result.run_id).token_totals == {"coordinator": 350}


def test_the_session_ceiling_carries_across_two_turns(
    seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dosimeter.graph.checkpointer import setup_checkpointer
    from tests.integration.test_checkpointer import database_settings

    setup_checkpointer(database_settings())
    coordinator_answers(
        monkeypatch,
        DispatchPlan(workers=[], rationale="nothing to dispatch"),
        input_tokens=700,
        output_tokens=300,
    )
    settings = settings_for_tests(bounds=Bounds(max_session_tokens=1000))

    first = run_assess(seeded, EXPOSURE, OFFICER, settings)
    second = run_assess(seeded, EXPOSURE, OFFICER, settings)

    first_record = queries.get_run_record(seeded, first.run_id)
    second_record = queries.get_run_record(seeded, second.run_id)
    second_detail = queries.run_record_detail(seeded, second.run_id)

    assert first.partial is None
    assert first_record.session_id == second_record.session_id
    assert queries.session_token_usage(seeded, first_record.session_id) == (700, 300)

    # the second turn spent nothing; the first turn's tokens are what stopped it
    assert second.outcome == "partial"
    assert second.partial["ceiling"] == "max_session_tokens"
    assert "max_session_tokens reached" in second.partial["message"]
    assert second_detail["model_calls"] == []
    assert [(event.stage, event.guardrail_id) for event in second_detail["guardrail_events"]] == [
        ("bounds", "max_session_tokens")
    ]
    assert queries.latest_dossier(seeded, EXPOSURE).payload["partial"]["ceiling"] == (
        "max_session_tokens"
    )


def test_trace_renders_what_the_turn_did_reading_only_from_postgres(seeded: Session) -> None:
    with correlation_scope("corr-trace"):
        recorder = recorder_for(seeded)
        recorder.dispatched("equipment", "the source would not retract")
        recorder.tool_called("find_similar_exposures", {"query_text": "retract"}, {"n": 2}, "ok")
        recorder.rule_invoked(
            "R2",
            "not_required",
            {"loss_of_control": False},
            threshold_named="20.2202(b)",
            dose_quantity="total_effective_dose_equivalent",
        )
        recorder.retrieved("retract failure", ["CFR-34#0003"], [0.77], ["in_force"])
        recorder.model_called("text-model-id", "reasoning", 100, 20, agent="equipment")
        recorder.reviewer_verdict(1, "equipment", "rejected", [{"reason": "no citation"}])
        recorder.trigger_evaluated("prompt_attack_filter_fired", fired=False)
        recorder.finish("complete")

    rendered = render_trace(seeded, EXPOSURE)

    assert "run record for EXP-2026-0412" in rendered
    assert "corr-trace" in rendered
    assert "equipment: the source would not retract" in rendered
    assert "find_similar_exposures -> ok" in rendered
    assert "R2: not_required on total_effective_dose_equivalent against 20.2202(b)" in rendered
    assert "CFR-34#0003 0.77 in_force" in rendered
    assert "iteration 1 on equipment: rejected" in rendered
    assert "objection: {'reason': 'no citation'}" in rendered
    assert "equipment: 120" in rendered


def test_the_record_checks_read_the_stored_record(seeded: Session) -> None:
    from dosimeter.evaluation.record_checks import run_checks

    recorder = recorder_for(seeded)
    recorder.rule_invoked("R1", "required", {"tede_rem": 26.0})
    recorder.retrieved("q", ["FR-DOSE#0001"], [0.9], ["proposed"])
    recorder.finish("complete")

    attribution, status = run_checks(seeded, recorder.run_id, ["R1", "R3"])

    assert attribution.passed is False
    assert attribution.offenders == ["R3"]
    assert status.passed is False
    assert status.offenders == ["FR-DOSE#0001"]
