"""Deterministic output guardrails for Dosimeter worker proposals."""

from collections.abc import Iterable

from dosimeter.domain.rules import RuleInvocation, RuleOutcome, RuleResult
from dosimeter.guardrails.models import (
    ClaimCitation,
    GuardrailOutcome,
    GuardrailResult,
    GuardrailViolation,
    SourceStatus,
)


def evaluate_output_guardrails(
    *,
    rule_results: Iterable[RuleResult],
    rule_invocations: Iterable[RuleInvocation],
    claim_citations: Iterable[ClaimCitation],
) -> GuardrailResult:
    """
    Validate structured regulatory output before it becomes actionable.

    Guardrails never calculate regulatory thresholds. R1-R5 remain the
    authoritative source of threshold outcomes.
    """

    results = tuple(rule_results)
    invocations = tuple(rule_invocations)
    citations = tuple(claim_citations)

    violations: list[GuardrailViolation] = []
    escalation_signals: list[str] = []

    _check_rule_invocations(
        results,
        invocations,
        violations,
    )

    _check_provenance(
        results,
        citations,
        violations,
    )

    _collect_escalation_signals(
        results,
        escalation_signals,
    )

    if violations:
        return GuardrailResult(
            outcome=GuardrailOutcome.BLOCK,
            violations=tuple(violations),
            escalation_signals=tuple(escalation_signals),
            explanation=(
                "Output was blocked because deterministic guardrail "
                "requirements were not satisfied."
            ),
        )

    if escalation_signals:
        return GuardrailResult(
            outcome=GuardrailOutcome.ESCALATE,
            violations=(),
            escalation_signals=tuple(escalation_signals),
            explanation=("Output requires human review before it can be finalized."),
        )

    return GuardrailResult(
        outcome=GuardrailOutcome.PASS,
        violations=(),
        escalation_signals=(),
        explanation="Output passed deterministic guardrail checks.",
    )


def _check_rule_invocations(
    results: tuple[RuleResult, ...],
    invocations: tuple[RuleInvocation, ...],
    violations: list[GuardrailViolation],
) -> None:
    """Every threshold outcome must match an invocation from this turn."""

    for result in results:
        matching_invocation = any(
            invocation.rule_id == result.rule_id and invocation.result == result
            for invocation in invocations
        )

        if matching_invocation:
            continue

        violations.append(
            GuardrailViolation(
                code="missing_or_mismatched_rule_invocation",
                message=(
                    f"{result.rule_id} does not match a recorded deterministic rule invocation."
                ),
            )
        )


def _check_provenance(
    results: tuple[RuleResult, ...],
    citations: tuple[ClaimCitation, ...],
    violations: list[GuardrailViolation],
) -> None:
    """Regulatory claims require claim-level, in-force provenance."""

    if results and not citations:
        violations.append(
            GuardrailViolation(
                code="missing_claim_provenance",
                message=(
                    "The proposal contains regulatory rule results but "
                    "has no claim-level provenance."
                ),
            )
        )
        return

    for citation in citations:
        if citation.source_status != SourceStatus.PROPOSED:
            continue

        violations.append(
            GuardrailViolation(
                code="proposed_source_determination",
                claim_id=citation.claim_id,
                message=(
                    f"{citation.claim_id} relies on proposed regulatory "
                    "material and cannot support a determination."
                ),
            )
        )


def _collect_escalation_signals(
    results: tuple[RuleResult, ...],
    escalation_signals: list[str],
) -> None:
    """Collect deterministic conditions requiring human review."""

    for result in results:
        if result.outcome == RuleOutcome.HUMAN_DETERMINATION:
            escalation_signals.append(f"{result.rule_id} requires human determination.")

        if result.outcome == RuleOutcome.INSUFFICIENT_DATA:
            fields = ", ".join(result.missing_fields)

            if fields:
                escalation_signals.append(f"{result.rule_id} has insufficient data: {fields}.")
            else:
                escalation_signals.append(f"{result.rule_id} has insufficient data.")

        if result.rule_id == "R4" and result.outcome == RuleOutcome.VALID:
            escalation_signals.append("R4 planned special exposure requires human review.")
