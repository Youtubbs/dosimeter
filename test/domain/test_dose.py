import pytest
from pydantic import ValidationError

from dosimeter.domain.dose import (
    DoseUnit,
    IntakeMultipleOfALI,
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    TotalEffectiveDoseEquivalent,
)


def test_create_p1_tede():
    tede = TotalEffectiveDoseEquivalent(
        value=6.2,
        unit=DoseUnit.REM,
    )

    assert tede.value == 6.2
    assert tede.unit == DoseUnit.REM


def test_create_p1_lens_dose():
    lens = LensDoseEquivalent(
        value=3.0,
        unit=DoseUnit.REM,
    )

    assert lens.value == 3.0
    assert lens.unit == DoseUnit.REM


def test_create_p1_shallow_dose():
    shallow = ShallowDoseEquivalent(
        value=11,
        unit=DoseUnit.REM,
    )

    assert shallow.value == 11
    assert shallow.unit == DoseUnit.REM


def test_negative_dose_is_rejected():
    with pytest.raises(ValidationError):
        TotalEffectiveDoseEquivalent(
            value=-1,
            unit=DoseUnit.REM,
        )


def test_negative_intake_multiple_is_rejected():
    with pytest.raises(ValidationError):
        IntakeMultipleOfALI(value=-1)
