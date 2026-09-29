"""Tests for deterministic output guardrails."""

import pytest

from dosimeter.domain.rules import (
    RuleInvocation,
    RuleOutcome,
    RuleResult,
)
from dosimeter.guardrails.models import (
    ClaimCitation,
    GuardrailOutcome,
    SourceStatus,
)
from dosimeter.guardrails.output import evaluate_output_guardrails


def make_result(
    rule_id: str,
    outcome: RuleOutcome,
    missing_fields: tuple[str, ...] = (),
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        outcome=outcome,
        sources=(),
        inputs_used={},
        explanation="Test regulatory determination.",
        missing_fields=missing_fields,
    )


def make_invocation(result: RuleResult) -> RuleInvocation:
    return RuleInvocation(
        rule_id=result.rule_id,
        inputs={},
        result=result,
        path="harness",
    )


def make_citation(
    *,
    claim_id: str = "claim-1",
    citation: str = "10 CFR Part 20",
    source_status: SourceStatus = SourceStatus.IN_FORCE,
) -> ClaimCitation:
    return ClaimCitation(
        claim_id=claim_id,
        citation=citation,
        source_status=source_status,
    )


def evaluate(
    result: RuleResult,
    *,
    include_invocation: bool = True,
    claim_citations: tuple[ClaimCitation, ...] | None = None,
):
    citations = (make_citation(),) if claim_citations is None else claim_citations

    return evaluate_output_guardrails(
        rule_results=(result,),
        rule_invocations=((make_invocation(result),) if include_invocation else ()),
        claim_citations=citations,
    )


def test_supported_output_passes():
    result = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
    )

    guardrail = evaluate(result)

    assert guardrail.outcome == GuardrailOutcome.PASS
    assert guardrail.violations == ()
    assert guardrail.escalation_signals == ()


def test_missing_rule_invocation_blocks():
    result = make_result(
        "R1",
        RuleOutcome.REQUIRED,
    )

    guardrail = evaluate(
        result,
        include_invocation=False,
    )

    assert guardrail.outcome == GuardrailOutcome.BLOCK

    assert any(
        violation.code == "missing_or_mismatched_rule_invocation"
        for violation in guardrail.violations
    )


def test_mismatched_rule_result_blocks():
    recorded = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
    )

    proposed = make_result(
        "R1",
        RuleOutcome.REQUIRED,
    )

    guardrail = evaluate_output_guardrails(
        rule_results=(proposed,),
        rule_invocations=(make_invocation(recorded),),
        claim_citations=(make_citation(),),
    )

    assert guardrail.outcome == GuardrailOutcome.BLOCK

    assert any(
        violation.code == "missing_or_mismatched_rule_invocation"
        for violation in guardrail.violations
    )


def test_missing_claim_provenance_blocks():
    result = make_result(
        "R1",
        RuleOutcome.REQUIRED,
    )

    guardrail = evaluate(
        result,
        claim_citations=(),
    )

    assert guardrail.outcome == GuardrailOutcome.BLOCK

    assert any(violation.code == "missing_claim_provenance" for violation in guardrail.violations)


def test_proposed_source_determination_blocks():
    result = make_result(
        "R1",
        RuleOutcome.REQUIRED,
    )

    citation = make_citation(
        claim_id="notification-claim",
        citation="Proposed regulatory material",
        source_status=SourceStatus.PROPOSED,
    )

    guardrail = evaluate(
        result,
        claim_citations=(citation,),
    )

    assert guardrail.outcome == GuardrailOutcome.BLOCK

    assert any(
        violation.code == "proposed_source_determination" for violation in guardrail.violations
    )


def test_proposed_source_violation_names_claim():
    result = make_result(
        "R3",
        RuleOutcome.REQUIRED,
    )

    citation = make_citation(
        claim_id="written-report-claim",
        citation="Proposed regulatory material",
        source_status=SourceStatus.PROPOSED,
    )

    guardrail = evaluate(
        result,
        claim_citations=(citation,),
    )

    violation = next(
        violation
        for violation in guardrail.violations
        if violation.code == "proposed_source_determination"
    )

    assert violation.claim_id == "written-report-claim"


def test_r5_human_determination_escalates():
    result = make_result(
        "R5",
        RuleOutcome.HUMAN_DETERMINATION,
    )

    guardrail = evaluate(result)

    assert guardrail.outcome == GuardrailOutcome.ESCALATE

    assert any("R5" in signal for signal in guardrail.escalation_signals)


def test_r4_valid_escalates():
    result = make_result(
        "R4",
        RuleOutcome.VALID,
    )

    guardrail = evaluate(result)

    assert guardrail.outcome == GuardrailOutcome.ESCALATE

    assert any("R4" in signal for signal in guardrail.escalation_signals)


def test_insufficient_data_escalates():
    result = make_result(
        "R2",
        RuleOutcome.INSUFFICIENT_DATA,
        missing_fields=("loss_of_control",),
    )

    guardrail = evaluate(result)

    assert guardrail.outcome == GuardrailOutcome.ESCALATE

    assert any("loss_of_control" in signal for signal in guardrail.escalation_signals)


def test_structural_violation_takes_priority():
    result = make_result(
        "R4",
        RuleOutcome.VALID,
    )

    guardrail = evaluate(
        result,
        include_invocation=False,
        claim_citations=(),
    )

    assert guardrail.outcome == GuardrailOutcome.BLOCK

    codes = {violation.code for violation in guardrail.violations}

    assert codes == {
        "missing_or_mismatched_rule_invocation",
        "missing_claim_provenance",
    }

    assert guardrail.escalation_signals


@pytest.mark.parametrize(
    "outcome",
    [
        RuleOutcome.REQUIRED,
        RuleOutcome.NOT_REQUIRED,
        RuleOutcome.PASS,
    ],
)
def test_supported_outcomes_pass(
    outcome: RuleOutcome,
):
    result = make_result(
        "R1",
        outcome,
    )

    guardrail = evaluate(result)

    assert guardrail.outcome == GuardrailOutcome.PASS
