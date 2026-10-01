"""Typed guardrail event records."""

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class GuardrailRemedy(StrEnum):
    """Deterministic action taken after a guardrail failure."""

    BLOCK_AND_ESCALATE = "block_and_escalate"
    REDACT = "redact"
    REGENERATE = "regenerate"
    APPEND_DISCLOSURE = "append_disclosure"
    RUN_RULE_AND_REGENERATE = "run_rule_and_regenerate"
    REFUSE_AND_LOG = "refuse_and_log"


class GuardrailEvent(BaseModel):
    """Machine-readable record of one guardrail failure."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    correlation_id: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    remedy: GuardrailRemedy
    source: str = Field(min_length=1)
    detail: str = Field(min_length=1)


def create_guardrail_event(
    *,
    trigger: str,
    remedy: GuardrailRemedy,
    source: str,
    detail: str,
    correlation_id: str | None = None,
) -> GuardrailEvent:
    """Create a deterministic structured guardrail event."""

    return GuardrailEvent(
        correlation_id=correlation_id or str(uuid4()),
        trigger=trigger,
        remedy=remedy,
        source=source,
        detail=detail,
    )
