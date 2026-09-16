""" Defines strongly typed radiation measurements. 
Instead of passing generic numbers through the system, TEDE, lens, shallow dose, and intake are different types that carry their value and unit. 
This stops the rules engine from accidentally evaluating one dose quantity against another quantity's regulatory threshold."."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DoseUnit(str, Enum):
    REM = "rem"
    RAD = "rad"

"""TEDE, lens, and shallow dose are not interchangeable and have different annual and notification thresholds 
    These are reped by three different Python types stored within four models 
"""

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
