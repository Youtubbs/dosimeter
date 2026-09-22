
"""
Tests for typed radiation dose quantities.

These tests verify that the dose domain models correctly represent
P1/P2 data and reject invalid or unsafe inputs.
"""

import pytest
from pydantic import ValidationError

from dosimeter.domain.dose import (
    DoseUnit,
    IntakeMultipleOfALI,
    LensDoseEquivalent,
    LensThreshold,
    ShallowDoseEquivalent,
    ShallowDoseSite,
    ShallowThreshold,
    TEDEThreshold,
    TotalEffectiveDoseEquivalent,
)

# ---------------------------------------------------------------------------
# P1 packet values
# ---------------------------------------------------------------------------
def test_create_p1_tede() -> None:
    dose = TotalEffectiveDoseEquivalent(
        value=6.2,
        unit=DoseUnit.REM,
    )

    assert dose.value == 6.2
    assert dose.unit == DoseUnit.REM


def test_create_p1_lens_dose() -> None:
    dose = LensDoseEquivalent(
        value=3.0,
        unit=DoseUnit.REM,
    )

    assert dose.value == 3.0
    assert dose.unit == DoseUnit.REM


def test_create_p1_shallow_dose() -> None:
    dose = ShallowDoseEquivalent(
        value=11.0,
        unit=DoseUnit.REM,
        site=ShallowDoseSite.EXTREMITY,
    )

    assert dose.value == 11.0
    assert dose.unit == DoseUnit.REM
    assert dose.site == ShallowDoseSite.EXTREMITY


# ---------------------------------------------------------------------------
# P2 packet values
# ---------------------------------------------------------------------------
def test_create_p2_tede() -> None:
    dose = TotalEffectiveDoseEquivalent(
        value=4.1,
        unit=DoseUnit.REM,
    )

    assert dose.value == 4.1
    assert dose.unit == DoseUnit.REM


def test_create_p2_lens_dose() -> None:
    dose = LensDoseEquivalent(
        value=9.0,
        unit=DoseUnit.REM,
    )

    assert dose.value == 9.0
    assert dose.unit == DoseUnit.REM


def test_create_p2_shallow_extremity_dose() -> None:
    dose = ShallowDoseEquivalent(
        value=310.0,
        unit=DoseUnit.RAD,
        site=ShallowDoseSite.EXTREMITY,
    )

    assert dose.value == 310.0
    assert dose.unit == DoseUnit.RAD
    assert dose.site == ShallowDoseSite.EXTREMITY


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
def test_create_intake_multiple_of_ali() -> None:
    intake = IntakeMultipleOfALI(value=1.5)

    assert intake.value == 1.5


# ---------------------------------------------------------------------------
# Supported units
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "unit",
    [
        DoseUnit.REM,
        DoseUnit.RAD,
        DoseUnit.SIEVERT,
        DoseUnit.GRAY,
    ],
)
def test_supported_dose_units(unit: DoseUnit) -> None:
    dose = TotalEffectiveDoseEquivalent(
        value=1.0,
        unit=unit,
    )

    assert dose.unit == unit


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_negative_tede_rejected() -> None:
    with pytest.raises(ValidationError):
        TotalEffectiveDoseEquivalent(
            value=-1.0,
            unit=DoseUnit.REM,
        )


def test_negative_lens_dose_rejected() -> None:
    with pytest.raises(ValidationError):
        LensDoseEquivalent(
            value=-1.0,
            unit=DoseUnit.REM,
        )


def test_negative_shallow_dose_rejected() -> None:
    with pytest.raises(ValidationError):
        ShallowDoseEquivalent(
            value=-1.0,
            unit=DoseUnit.REM,
            site=ShallowDoseSite.SKIN,
        )


def test_negative_intake_rejected() -> None:
    with pytest.raises(ValidationError):
        IntakeMultipleOfALI(value=-1.0)


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        TotalEffectiveDoseEquivalent.model_validate(
            {
                "value": 6.2,
                "unit": DoseUnit.REM,
                "unexpected_field": "not allowed",
            }
        )


def test_invalid_unit_rejected() -> None:
    with pytest.raises(ValidationError):
        TotalEffectiveDoseEquivalent.model_validate(
            {
                "value": 6.2,
                "unit": "banana",
            }
        )


def test_invalid_shallow_site_rejected() -> None:
    with pytest.raises(ValidationError):
        ShallowDoseEquivalent.model_validate(
            {
                "value": 11.0,
                "unit": DoseUnit.REM,
                "site": "unknown",
            }
        )


# ---------------------------------------------------------------------------
# Frozen / immutable models
# ---------------------------------------------------------------------------
def test_tede_is_frozen() -> None:
    dose = TotalEffectiveDoseEquivalent(
        value=6.2,
        unit=DoseUnit.REM,
    )

    with pytest.raises(ValidationError):
        dose.value = 100.0  # type: ignore[misc]


def test_shallow_dose_is_frozen() -> None:
    dose = ShallowDoseEquivalent(
        value=310.0,
        unit=DoseUnit.RAD,
        site=ShallowDoseSite.EXTREMITY,
    )

    with pytest.raises(ValidationError):
        dose.site = ShallowDoseSite.SKIN  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Typed thresholds
# ---------------------------------------------------------------------------
def test_create_tede_threshold() -> None:
    threshold = TEDEThreshold(
        value=25.0,
        unit=DoseUnit.REM,
    )

    assert threshold.value == 25.0
    assert threshold.unit == DoseUnit.REM


def test_create_lens_threshold() -> None:
    threshold = LensThreshold(
        value=75.0,
        unit=DoseUnit.REM,
    )

    assert threshold.value == 75.0
    assert threshold.unit == DoseUnit.REM


def test_create_shallow_threshold() -> None:
    threshold = ShallowThreshold(
        value=250.0,
        unit=DoseUnit.RAD,
    )

    assert threshold.value == 250.0
    assert threshold.unit == DoseUnit.RAD


# ---------------------------------------------------------------------------
# Bare-number protection
# ---------------------------------------------------------------------------
def requires_tede(dose: TotalEffectiveDoseEquivalent) -> float:
    """
    Example runtime boundary showing that callers must provide
    a typed TEDE object rather than a bare number.
    """

    if not isinstance(dose, TotalEffectiveDoseEquivalent):
        raise TypeError(
            "Expected TotalEffectiveDoseEquivalent."
        )

    return dose.value


def test_typed_tede_is_accepted() -> None:
    dose = TotalEffectiveDoseEquivalent(
        value=6.2,
        unit=DoseUnit.REM,
    )

    assert requires_tede(dose) == 6.2


def test_bare_float_is_rejected_where_tede_expected() -> None:
    with pytest.raises(TypeError):
        requires_tede(6.2)  # type: ignore[arg-type]


def test_bare_int_is_rejected_where_tede_expected() -> None:
    with pytest.raises(TypeError):
        requires_tede(6)  # type: ignore[arg-type]
