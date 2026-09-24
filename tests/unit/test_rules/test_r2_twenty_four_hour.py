"""Unit tests for R2 twenty-four-hour notification."""

import pytest

from dosimeter.domain.dose import (
    DoseUnit,
    IntakeMultipleOfALI,
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    ShallowDoseSite,
    TotalEffectiveDoseEquivalent,
)
from dosimeter.domain.rules import RuleOutcome
from dosimeter.rules.r2_twenty_four_hour import evaluate_r2


def make_tede(value: float) -> TotalEffectiveDoseEquivalent:
    return TotalEffectiveDoseEquivalent(
        value=value,
        unit=DoseUnit.REM,
    )


def make_lens(value: float) -> LensDoseEquivalent:
    return LensDoseEquivalent(
        value=value,
        unit=DoseUnit.REM,
    )


def make_shallow(value: float) -> ShallowDoseEquivalent:
    return ShallowDoseEquivalent(
        value=value,
        unit=DoseUnit.REM,
        site=ShallowDoseSite.EXTREMITY,
    )


def make_intake(value: float) -> IntakeMultipleOfALI:
    return IntakeMultipleOfALI(value=value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.99, RuleOutcome.NOT_REQUIRED),
        (5.00, RuleOutcome.NOT_REQUIRED),
        (5.01, RuleOutcome.REQUIRED),
    ],
)
def test_r2_tede_uses_strict_greater_than(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r2(
        loss_of_control=True,
        tede=make_tede(value),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (14.99, RuleOutcome.NOT_REQUIRED),
        (15.00, RuleOutcome.NOT_REQUIRED),
        (15.01, RuleOutcome.REQUIRED),
    ],
)
def test_r2_lens_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r2(
        loss_of_control=True,
        tede=make_tede(0.0),
        lens=make_lens(value),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (49.99, RuleOutcome.NOT_REQUIRED),
        (50.00, RuleOutcome.NOT_REQUIRED),
        (50.01, RuleOutcome.REQUIRED),
    ],
)
def test_r2_shallow_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r2(
        loss_of_control=True,
        tede=make_tede(0.0),
        lens=make_lens(0.0),
        shallow=make_shallow(value),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.99, RuleOutcome.NOT_REQUIRED),
        (1.00, RuleOutcome.NOT_REQUIRED),
        (1.01, RuleOutcome.REQUIRED),
    ],
)
def test_r2_intake_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r2(
        loss_of_control=True,
        tede=make_tede(0.0),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(value),
    )

    assert result.outcome == expected


def test_r2_requires_loss_of_control() -> None:
    result = evaluate_r2(
        loss_of_control=False,
        tede=make_tede(6.2),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.NOT_REQUIRED


def test_r2_missing_loss_of_control_is_insufficient_data() -> None:
    result = evaluate_r2(
        loss_of_control=None,
        tede=make_tede(6.2),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert "loss_of_control" in result.missing_fields


def test_r2_records_multiple_triggered_conditions() -> None:
    result = evaluate_r2(
        loss_of_control=True,
        tede=make_tede(6.0),
        lens=make_lens(16.0),
        shallow=make_shallow(51.0),
        intake=make_intake(2.0),
    )

    assert result.outcome == RuleOutcome.REQUIRED
    assert result.failing_conditions == (
        "tede",
        "lens",
        "shallow",
        "intake",
    )
