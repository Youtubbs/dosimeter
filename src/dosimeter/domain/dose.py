"""
Typed radiation dose quantities used by the Dosimeter application.

Dose values are represented as specific quantity types rather than bare
floats so that TEDE, lens dose, and shallow dose cannot be treated as
interchangeable measurements.
"""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

# Enumerations
class DoseUnit(str, Enum):
    """Supported radiation dose units."""

    REM = "rem"
    RAD = "rad"
    SIEVERT = "Sv"
    GRAY = "Gy"


class ShallowDoseSite(str, Enum):
    """Location associated with a shallow-dose measurement."""

    SKIN = "skin"
    EXTREMITY = "extremity"


# Dose Quantities
class TotalEffectiveDoseEquivalent(BaseModel):
    """Total Effective Dose Equivalent (TEDE)."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit


class LensDoseEquivalent(BaseModel):
    """Lens Dose Equivalent."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit


class ShallowDoseEquivalent(BaseModel):
    """Shallow-Dose Equivalent for the skin or an extremity."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit
    site: ShallowDoseSite


class IntakeMultipleOfALI(BaseModel):
    """Intake expressed as a multiple of the Annual Limit on Intake (ALI)."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)


# Typed Thresholds
class TEDEThreshold(BaseModel):
    """Threshold that may only be used with TEDE measurements."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit


class LensThreshold(BaseModel):
    """Threshold that may only be used with lens-dose measurements."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit


class ShallowThreshold(BaseModel):
    """Threshold that may only be used with shallow-dose measurements."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    value: float = Field(ge=0)
    unit: DoseUnit
