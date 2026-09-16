from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DoseUnit(str, Enum):
    REM = "rem"
    RAD = "rad"


class TotalEffectiveDoseEquivalent(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0)
    unit: DoseUnit


class LensDoseEquivalent(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0)
    unit: DoseUnit


class ShallowDoseEquivalent(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0)
    unit: DoseUnit


class IntakeMultipleOfALI(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0)
