"""Deterministic remedies for output guardrail violations."""

from dosimeter.guardrails.events import (
    GuardrailEvent,
    GuardrailRemedy,
    create_guardrail_event,
)
from dosimeter.guardrails.models import GuardrailResult


def events_from_guardrail_result(
    result: GuardrailResult,
    *,
    source: str,
    correlation_id: str,
) -> tuple[GuardrailEvent, ...]:
    """Convert output violations into auditable guardrail events."""

    events: list[GuardrailEvent] = []

    for violation in result.violations:
        remedy = _remedy_for_violation(violation.code)

        detail = violation.message

        if violation.claim_id:
            detail = f"{violation.claim_id}: {detail}"

        events.append(
            create_guardrail_event(
                correlation_id=correlation_id,
                trigger=violation.code,
                remedy=remedy,
                source=source,
                detail=detail,
            )
        )

    return tuple(events)


def _remedy_for_violation(
    code: str,
) -> GuardrailRemedy:
    """Return the required deterministic remedy for a violation."""

    if code == "missing_or_mismatched_rule_invocation":
        return GuardrailRemedy.RUN_RULE_AND_REGENERATE

    if code == "missing_claim_provenance":
        return GuardrailRemedy.REGENERATE

    if code == "proposed_source_determination":
        return GuardrailRemedy.BLOCK_AND_ESCALATE

    return GuardrailRemedy.BLOCK_AND_ESCALATE
