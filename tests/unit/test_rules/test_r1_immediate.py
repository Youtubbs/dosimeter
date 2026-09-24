"""Unit test for R1 immediate-notification rule."""

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
from dosimeter.rules.r1_immediate import evaluate_r1


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
        unit=DoseUnit.RAD,
        site=ShallowDoseSite.EXTREMITY,
    )


def make_intake(value: float) -> IntakeMultipleOfALI:
    return IntakeMultipleOfALI(value=value)


# ---------------------------------------------------------------------------
#  THE TEDE boundary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (24.99, RuleOutcome.NOT_REQUIRED),
        (25.00, RuleOutcome.REQUIRED),
        (25.01, RuleOutcome.REQUIRED),
    ],
)
def test_r1_tede_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r1(
        tede=make_tede(value),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# THE Lens boundary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (74.99, RuleOutcome.NOT_REQUIRED),
        (75.00, RuleOutcome.REQUIRED),
        (75.01, RuleOutcome.REQUIRED),
    ],
)
def test_r1_lens_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r1(
        tede=make_tede(0.0),
        lens=make_lens(value),
        shallow=make_shallow(0.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# THE Shallow-dose boundary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (249.99, RuleOutcome.NOT_REQUIRED),
        (250.00, RuleOutcome.REQUIRED),
        (250.01, RuleOutcome.REQUIRED),
    ],
)
def test_r1_shallow_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r1(
        tede=make_tede(0.0),
        lens=make_lens(0.0),
        shallow=make_shallow(value),
        intake=make_intake(0.0),
    )

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# THE Intake boundary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.99, RuleOutcome.NOT_REQUIRED),
        (5.00, RuleOutcome.REQUIRED),
        (5.01, RuleOutcome.REQUIRED),
    ],
)
def test_r1_intake_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    result = evaluate_r1(
        tede=make_tede(0.0),
        lens=make_lens(0.0),
        shallow=make_shallow(0.0),
        intake=make_intake(value),
    )

    assert result.outcome == expected


# ---------------------------------------------------------------------------
#  Missing-data behavior
# ---------------------------------------------------------------------------
def test_r1_missing_input_returns_insufficient_data() -> None:
    result = evaluate_r1(
        tede=make_tede(6.2),
        lens=None,
        shallow=make_shallow(11.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert "lens" in result.missing_fields


def test_r1_reports_all_missing_inputs() -> None:
    result = evaluate_r1(
        tede=None,
        lens=None,
        shallow=make_shallow(11.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert result.missing_fields == ("tede", "lens")


# ---------------------------------------------------------------------------
# Packet fixtures
# ---------------------------------------------------------------------------
def test_r1_p1_does_not_require_immediate_notification() -> None:
    """P1 remains below all R1 immediate-notification thresholds."""

    result = evaluate_r1(
        tede=make_tede(6.2),
        lens=make_lens(3.0),
        shallow=make_shallow(11.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.NOT_REQUIRED


def test_r1_p2_requires_immediate_notification() -> None:
    """P2 triggers R1 because shallow dose is 310 rad."""

    result = evaluate_r1(
        tede=make_tede(4.1),
        lens=make_lens(9.0),
        shallow=make_shallow(310.0),
        intake=make_intake(0.0),
    )

    assert result.outcome == RuleOutcome.REQUIRED
    assert "shallow" in result.failing_conditions


# ---------------------------------------------------------------------------
# Multiple simultaneous triggers
# ---------------------------------------------------------------------------
def test_r1_records_multiple_triggered_thresholds() -> None:
    result = evaluate_r1(
        tede=make_tede(30.0),
        lens=make_lens(80.0),
        shallow=make_shallow(300.0),
        intake=make_intake(6.0),
    )

    assert result.outcome == RuleOutcome.REQUIRED

    assert result.failing_conditions == (
        "tede",
        "lens",
        "shallow",
        "intake",
    )
