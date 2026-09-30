from dosimeter.guardrails.events import (
    GuardrailRemedy,
    create_guardrail_event,
)
from dosimeter.harness.assess import dossier_payload


def test_dossier_payload_records_guardrail_events():
    event = create_guardrail_event(
        correlation_id="corr-123",
        trigger="prompt_attack_filter_fired",
        remedy=GuardrailRemedy.BLOCK_AND_ESCALATE,
        source="artifact:P3/crew-note.txt",
        detail="Bedrock Prompt Attack filter intervened.",
    )

    state = {
        "proposals": {},
        "rule_invocations": [],
        "retrieval_log": [],
        "reviewer_verdicts": [],
        "guardrail_events": [event],
        "outcome": "escalated",
    }

    payload = dossier_payload(
        state,
        exposure_id="EXP-001",
    )

    assert len(payload["guardrail_events"]) == 1

    stored = payload["guardrail_events"][0]

    assert stored["correlation_id"] == "corr-123"
    assert stored["trigger"] == "prompt_attack_filter_fired"
    assert stored["remedy"] == "block_and_escalate"
    assert stored["source"] == "artifact:P3/crew-note.txt"


def test_guardrail_event_can_be_mapped_to_run_record_fields():
    event = create_guardrail_event(
        correlation_id="corr-456",
        trigger="proposed_source_determination",
        remedy=GuardrailRemedy.BLOCK_AND_ESCALATE,
        source="worker:written_report",
        detail="claim-2 relies on proposed regulatory material.",
    )

    stage = "output"
    action = event.remedy.value
    guardrail_id = event.trigger
    detail = {
        "correlation_id": event.correlation_id,
        "trigger": event.trigger,
        "source": event.source,
        "detail": event.detail,
    }

    assert stage == "output"
    assert action == "block_and_escalate"
    assert guardrail_id == "proposed_source_determination"
    assert detail["correlation_id"] == "corr-456"
    assert detail["source"] == "worker:written_report"
