"""
Tests for shared deterministic rule contracts.
"""

import pytest
from pydantic import ValidationError

from dosimeter.domain.rules import (
    RuleInvocation,
    RuleOutcome,
    RuleResult,
    RuleSource,
)


def make_source() -> RuleSource:
    """Create a reusable regulatory source for unit tests."""

    return RuleSource(
        citation="10 CFR 20.2202(a)",
        section="Immediate notification",
        status="in_force",
    )


def make_result() -> RuleResult:
    """Create a reusable R1 result for unit tests."""

    return RuleResult(
        rule_id="R1",
        outcome=RuleOutcome.REQUIRED,
        sources=(make_source(),),
        inputs_used={
            "shallow_dose": "310 rad",
        },
        threshold={
            "shallow_dose": "250 rad",
        },
        explanation=(
            "The shallow-dose value met the immediate "
            "notification threshold."
        ),
    )


def test_create_rule_source() -> None:
    source = make_source()

    assert source.citation == "10 CFR 20.2202(a)"
    assert source.section == "Immediate notification"
    assert source.status == "in_force"


def test_create_rule_result() -> None:
    result = make_result()

    assert result.rule_id == "R1"
    assert result.outcome == RuleOutcome.REQUIRED
    assert len(result.sources) == 1

    assert result.inputs_used["shallow_dose"] == "310 rad"
    assert result.threshold == {
        "shallow_dose": "250 rad",
    }

    assert result.failing_conditions == ()
    assert result.missing_fields == ()


def test_create_rule_invocation() -> None:
    result = make_result()

    invocation = RuleInvocation(
        rule_id="R1",
        inputs={
            "shallow_dose": "310 rad",
        },
        result=result,
    )

    assert invocation.rule_id == "R1"
    assert invocation.result == result
    assert invocation.result.outcome == RuleOutcome.REQUIRED


def test_insufficient_data_result() -> None:
    result = RuleResult(
        rule_id="R2",
        outcome=RuleOutcome.INSUFFICIENT_DATA,
        sources=(make_source(),),
        inputs_used={},
        explanation="Required exposure information is missing.",
        missing_fields=(
            "loss_of_control",
            "tede",
        ),
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert "loss_of_control" in result.missing_fields
    assert "tede" in result.missing_fields


def test_failed_conditions_are_preserved() -> None:
    result = RuleResult(
        rule_id="R4",
        outcome=RuleOutcome.INVALID,
        sources=(make_source(),),
        inputs_used={},
        explanation="One or more PSE conditions failed.",
        failing_conditions=(
            "condition_c",
            "condition_e",
        ),
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == (
        "condition_c",
        "condition_e",
    )


def test_rule_source_rejects_empty_citation() -> None:
    with pytest.raises(ValidationError):
        RuleSource(
            citation="",
            section="Immediate notification",
            status="in_force",
        )


def test_rule_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RuleResult.model_validate(
            {
                "rule_id": "R1",
                "outcome": RuleOutcome.REQUIRED,
                "sources": [make_source()],
                "inputs_used": {},
                "explanation": "Test result.",
                "unexpected_field": "not allowed",
            }
        )


def test_rule_result_is_frozen() -> None:
    result = make_result()

    with pytest.raises(ValidationError):
        result.rule_id = "R99"  # type: ignore[misc]
