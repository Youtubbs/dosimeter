"""Typed contracts for deterministic output guardrails."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GuardrailOutcome(StrEnum):
    """Possible results from an output guardrail check."""

    PASS = "pass"  # noqa: S105
    ESCALATE = "escalate"
    BLOCK = "block"


class SourceStatus(StrEnum):
    """Regulatory status carried with a cited source."""

    IN_FORCE = "in_force"
    PROPOSED = "proposed"


class ClaimCitation(BaseModel):
    """Machine-checkable provenance attached to one output claim."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    claim_id: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    source_status: SourceStatus


class GuardrailViolation(BaseModel):
    """One specific problem found while validating an output."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    claim_id: str | None = None


class GuardrailResult(BaseModel):
    """Structured result returned by the output guardrails."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    outcome: GuardrailOutcome
    violations: tuple[GuardrailViolation, ...] = ()
    escalation_signals: tuple[str, ...] = ()
    explanation: str = Field(min_length=1)
