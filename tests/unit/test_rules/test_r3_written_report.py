"""Unit tests for R3 written-report determination."""

import pytest

from dosimeter.domain.dose import (
    DoseUnit,
    EmbryoFetusDoseEquivalent,
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    ShallowDoseSite,
    TotalEffectiveDoseEquivalent,
    UnrestrictedAreaDose,
)
from dosimeter.domain.rules import RuleOutcome
from dosimeter.rules.r3_written_report import (
    ExposurePopulation,
    R3Inputs,
    evaluate_r3,
)
# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
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


def make_embryo_fetus(value: float) -> EmbryoFetusDoseEquivalent:
    return EmbryoFetusDoseEquivalent(
        value=value,
        unit=DoseUnit.REM,
    )


def make_unrestricted(value: float) -> UnrestrictedAreaDose:
    return UnrestrictedAreaDose(
        value=value,
        unit=DoseUnit.REM,
    )


def make_adult_inputs(
    *,
    annual_tede: float = 0.0,
    annual_lens: float = 0.0,
    annual_shallow: float = 0.0,
    r1_required: bool = False,
    r2_required: bool = False,
) -> R3Inputs:
    return R3Inputs(
        r1_required=r1_required,
        r2_required=r2_required,
        population=ExposurePopulation.ADULT_WORKER,
        annual_tede=make_tede(annual_tede),
        annual_lens=make_lens(annual_lens),
        annual_shallow=make_shallow(annual_shallow),
    )


# ---------------------------------------------------------------------------
# R1 / R2 notification path
# ---------------------------------------------------------------------------
def test_r3_required_when_r1_required() -> None:
    inputs = make_adult_inputs(
        r1_required=True,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert "r1_notification_required" in result.failing_conditions


def test_r3_required_when_r2_required() -> None:
    inputs = make_adult_inputs(
        r2_required=True,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert "r2_notification_required" in result.failing_conditions


def test_r3_records_both_notification_paths() -> None:
    inputs = make_adult_inputs(
        r1_required=True,
        r2_required=True,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert result.failing_conditions == (
        "r1_notification_required",
        "r2_notification_required",
    )


# ---------------------------------------------------------------------------
# Adult-worker limits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.99, RuleOutcome.NOT_REQUIRED),
        (5.00, RuleOutcome.NOT_REQUIRED),
        (5.01, RuleOutcome.REQUIRED),
    ],
)
def test_r3_adult_tede_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = make_adult_inputs(
        annual_tede=value,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (14.99, RuleOutcome.NOT_REQUIRED),
        (15.00, RuleOutcome.NOT_REQUIRED),
        (15.01, RuleOutcome.REQUIRED),
    ],
)
def test_r3_adult_lens_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = make_adult_inputs(
        annual_lens=value,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (49.99, RuleOutcome.NOT_REQUIRED),
        (50.00, RuleOutcome.NOT_REQUIRED),
        (50.01, RuleOutcome.REQUIRED),
    ],
)
def test_r3_adult_shallow_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = make_adult_inputs(
        annual_shallow=value,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# P1
# ---------------------------------------------------------------------------
def test_r3_p1_requires_written_report() -> None:
    """P1 exceeds the adult annual TEDE limit."""

    inputs = make_adult_inputs(
        annual_tede=6.2,
        annual_lens=3.0,
        annual_shallow=11.0,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert "annual_tede" in result.failing_conditions


# ---------------------------------------------------------------------------
# P2
# ---------------------------------------------------------------------------
def test_r3_p2_required_because_r1_required() -> None:
    """P2 reaches R3 through its R1 notification requirement."""

    inputs = make_adult_inputs(
        r1_required=True,
        annual_tede=4.1,
        annual_lens=9.0,
        annual_shallow=0.0,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert "r1_notification_required" in result.failing_conditions


# ---------------------------------------------------------------------------
# Minor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.49, RuleOutcome.NOT_REQUIRED),
        (0.50, RuleOutcome.NOT_REQUIRED),
        (0.51, RuleOutcome.REQUIRED),
    ],
)
def test_r3_minor_tede_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.MINOR,
        annual_tede=make_tede(value),
        annual_lens=make_lens(0.0),
        annual_shallow=make_shallow(0.0),
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# Declared pregnant worker
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.49, RuleOutcome.NOT_REQUIRED),
        (0.50, RuleOutcome.NOT_REQUIRED),
        (0.51, RuleOutcome.REQUIRED),
    ],
)
def test_r3_embryo_fetus_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.DECLARED_PREGNANT_WORKER,
        embryo_fetus_dose=make_embryo_fetus(value),
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# Member of public
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.09, RuleOutcome.NOT_REQUIRED),
        (0.10, RuleOutcome.NOT_REQUIRED),
        (0.11, RuleOutcome.REQUIRED),
    ],
)
def test_r3_public_dose_boundary(
    value: float,
    expected: RuleOutcome,
) -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.MEMBER_OF_PUBLIC,
        annual_tede=make_tede(value),
    )

    result = evaluate_r3(inputs)

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# Unrestricted area
# ---------------------------------------------------------------------------
def test_r3_unrestricted_area_over_ten_times_limit() -> None:
    inputs = make_adult_inputs()

    inputs = inputs.model_copy(
        update={
            "unrestricted_area_dose": make_unrestricted(1.01),
        }
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED
    assert "unrestricted_area_dose" in result.failing_conditions


def test_r3_unrestricted_area_exactly_ten_times_limit_not_required() -> None:
    inputs = make_adult_inputs()

    inputs = inputs.model_copy(
        update={
            "unrestricted_area_dose": make_unrestricted(1.0),
        }
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.NOT_REQUIRED


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------
def test_r3_missing_adult_annual_data_is_insufficient() -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.ADULT_WORKER,
        annual_tede=make_tede(4.0),
        annual_lens=None,
        annual_shallow=None,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert result.missing_fields == (
        "annual_lens",
        "annual_shallow",
    )


def test_r3_missing_embryo_fetus_dose_is_insufficient() -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.DECLARED_PREGNANT_WORKER,
        embryo_fetus_dose=None,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert result.missing_fields == ("embryo_fetus_dose",)


# ---------------------------------------------------------------------------
# Planned Special Exposure
# ---------------------------------------------------------------------------
def test_r3_valid_pse_uses_alternate_reporting_path() -> None:
    inputs = R3Inputs(
        r1_required=False,
        r2_required=False,
        population=ExposurePopulation.ADULT_WORKER,
        annual_tede=make_tede(8.5),
        annual_lens=make_lens(0.0),
        annual_shallow=make_shallow(0.0),
        planned_special_exposure_valid=True,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.NOT_REQUIRED

    citations = {source.citation for source in result.sources}

    assert "10 CFR 20.1206" in citations
    assert "10 CFR 20.2204" in citations


# ---------------------------------------------------------------------------
# Multiple exceeded annual limits
# ---------------------------------------------------------------------------
def test_r3_records_multiple_exceeded_limits() -> None:
    inputs = make_adult_inputs(
        annual_tede=6.0,
        annual_lens=16.0,
        annual_shallow=51.0,
    )

    result = evaluate_r3(inputs)

    assert result.outcome == RuleOutcome.REQUIRED

    assert result.failing_conditions == (
        "annual_tede",
        "annual_lens",
        "annual_shallow",
    )
