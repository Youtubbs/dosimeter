"""Tests for deterministic guardrail remedies."""

from dosimeter.guardrails.events import GuardrailRemedy
from dosimeter.guardrails.models import (
    GuardrailOutcome,
    GuardrailResult,
    GuardrailViolation,
)
from dosimeter.guardrails.remedies import events_from_guardrail_result


def make_result(
    violation: GuardrailViolation,
) -> GuardrailResult:
    return GuardrailResult(
        outcome=GuardrailOutcome.BLOCK,
        violations=(violation,),
        explanation="Output blocked.",
    )


def test_missing_rule_invocation_runs_rule_and_regenerates():
    result = make_result(
        GuardrailViolation(
            code="missing_or_mismatched_rule_invocation",
            message="R1 was not invoked.",
        )
    )

    events = events_from_guardrail_result(
        result,
        source="worker:notification",
        correlation_id="corr-123",
    )

    assert len(events) == 1

    event = events[0]

    assert event.remedy == GuardrailRemedy.RUN_RULE_AND_REGENERATE
    assert event.trigger == "missing_or_mismatched_rule_invocation"
    assert event.correlation_id == "corr-123"


def test_missing_provenance_regenerates():
    result = make_result(
        GuardrailViolation(
            code="missing_claim_provenance",
            message="Claim has no provenance.",
        )
    )

    events = events_from_guardrail_result(
        result,
        source="worker:written_report",
        correlation_id="corr-456",
    )

    assert events[0].remedy == GuardrailRemedy.REGENERATE


def test_proposed_source_blocks_and_escalates():
    result = make_result(
        GuardrailViolation(
            code="proposed_source_determination",
            claim_id="claim-7",
            message="Proposed material cannot support determination.",
        )
    )

    events = events_from_guardrail_result(
        result,
        source="worker:notification",
        correlation_id="corr-789",
    )

    event = events[0]

    assert event.remedy == GuardrailRemedy.BLOCK_AND_ESCALATE
    assert event.trigger == "proposed_source_determination"
    assert "claim-7" in event.detail


def test_multiple_violations_create_multiple_events():
    result = GuardrailResult(
        outcome=GuardrailOutcome.BLOCK,
        violations=(
            GuardrailViolation(
                code="missing_claim_provenance",
                message="Missing provenance.",
            ),
            GuardrailViolation(
                code="proposed_source_determination",
                claim_id="claim-2",
                message="Proposed source.",
            ),
        ),
        explanation="Output blocked.",
    )

    events = events_from_guardrail_result(
        result,
        source="worker:written_report",
        correlation_id="corr-999",
    )

    assert len(events) == 2

    assert events[0].remedy == GuardrailRemedy.REGENERATE
    assert events[1].remedy == GuardrailRemedy.BLOCK_AND_ESCALATE

    assert all(event.correlation_id == "corr-999" for event in events)
