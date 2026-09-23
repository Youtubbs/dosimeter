"""
Shared domain contracts for regulatory rules.

Regulatory rules return structured RuleResult obj than bools.
 This preserves the rule outcome, regulatory source, inputs,
threshold information, missing fields, and failed conditions for later
workers, reviewers, guardrails, evaluation, and dossier gen.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleOutcome(str, Enum):
    """Supported outcomes from deterministic regulatory rules."""

    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    VALID = "valid"
    INVALID = "invalid"
    INSUFFICIENT_DATA = "insufficient_data"
    HUMAN_DETERMINATION = "human_determination"
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    

class RuleSource(BaseModel):
    """Regulatory source supporting a rule evaluation."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    citation: str = Field(min_length=1)
    section: str = Field(min_length=1)
    status: str = Field(min_length=1)


class RuleResult(BaseModel):
    """
    This is the result returned by regulatory rule.

    A RuleResult preserves enough info to explain what rule was
    evaluated, what evidence was used, what threshold was considered,
    and whether any required information or conditions were missing.
    """

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    rule_id: str = Field(min_length=1)

    outcome: RuleOutcome

    sources: tuple[RuleSource, ...]

    inputs_used: dict[str, Any]

    threshold: dict[str, Any] | None = None

    explanation: str = Field(min_length=1)

    failing_conditions: tuple[str, ...] = ()

    missing_fields: tuple[str, ...] = ()


class RuleInvocation(BaseModel):
    """
    Traceable record showing that a rule was invoked.

    This allows later components to verify which rule was called,
    which inputs were supplied, and what structured result it returned.
    """

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    rule_id: str = Field(min_length=1)

    inputs: dict[str, Any]

    result: RuleResult
