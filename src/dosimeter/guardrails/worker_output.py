"""Output-guardrail adapter for typed worker proposals.

This module bridges worker invocation history to the deterministic output
guardrail. It does not evaluate regulatory thresholds. Those remain inside
the R1-R5 rules engine.
"""

from collections.abc import Iterable
from typing import Any

from dosimeter.redaction import redact_value
from dosimeter.domain.rules import RuleInvocation, RuleResult
from dosimeter.guardrails.models import ClaimCitation, SourceStatus
from dosimeter.guardrails.output import evaluate_output_guardrails
from dosimeter.guardrails.remedies import events_from_guardrail_result
from dosimeter.tools.dispatcher import InvocationRecord
from dosimeter.guardrails.events import (
    GuardrailEvent,
    GuardrailRemedy,
    create_guardrail_event,
)


def evaluate_worker_output(
    *,
    rule_results: Iterable[RuleResult],
    invocations: Iterable[InvocationRecord],
    source: str,
    correlation_id: str,
) -> tuple[GuardrailEvent, ...]:
    """Evaluate one worker's structured regulatory output.

    Successful evaluate_rule tool calls are reconstructed as typed
    RuleInvocation objects. Claim-level provenance is derived from the
    regulatory sources already attached to each RuleResult.
    """

    results = tuple(rule_results)

    rule_invocations = _rule_invocations(invocations)
    claim_citations = _claim_citations(results)

    guardrail_result = evaluate_output_guardrails(
        rule_results=results,
        rule_invocations=rule_invocations,
        claim_citations=claim_citations,
    )

    return events_from_guardrail_result(
        guardrail_result,
        source=source,
        correlation_id=correlation_id,
    )


def _rule_invocations(
    invocations: Iterable[InvocationRecord],
) -> tuple[RuleInvocation, ...]:
    """Return successful deterministic rule invocations from this worker."""

    collected: list[RuleInvocation] = []

    for invocation in invocations:
        if (
            invocation.tool != "evaluate_rule"
            or invocation.outcome != "ok"
            or invocation.result is None
        ):
            continue

        collected.append(
            RuleInvocation.model_validate(invocation.result)
        )

    return tuple(collected)


def _claim_citations(
    rule_results: Iterable[RuleResult],
) -> tuple[ClaimCitation, ...]:
    """Build machine-checkable provenance from deterministic rule sources."""

    citations: list[ClaimCitation] = []

    for result in rule_results:
        for source in result.sources:
            citations.append(
                ClaimCitation(
                    claim_id=result.rule_id,
                    citation=source.citation,
                    source_status=SourceStatus(source.status),
                )
            )

    return tuple(citations)


def redact_worker_output(
    payload: dict[str, Any],
    *,
    source: str,
    correlation_id: str,
) -> tuple[dict[str, Any], tuple[GuardrailEvent, ...]]:
    """Redact sensitive output fields and record every redaction event."""

    redaction = redact_value(payload)

    if not redaction.removed:
        return redaction.value, ()

    events = tuple(
        create_guardrail_event(
            correlation_id=correlation_id,
            trigger="pii_redacted",
            remedy=GuardrailRemedy.REDACT,
            source=source,
            detail=f"Sensitive field redacted from output: {span.field_name}.",
        )
        for span in redaction.removed
    )

    return redaction.value, events
