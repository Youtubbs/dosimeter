"""Models for the deterministic golden evaluation set."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoldenCategory(StrEnum):
    """Required golden-set evaluation categories."""

    SINGLE_DOCUMENT = "single_document"
    MULTI_HOP = "multi_hop"
    THRESHOLD = "threshold"
    EXPOSURE_BACKED = "exposure_backed"
    REFUSAL = "refusal"
    DETERMINATION = "determination"
    ADVERSARIAL = "adversarial"
    NEAR_MISS = "near_miss"
    ESCALATION = "escalation"
    MULTI_TURN = "multi_turn"


class GoldenSource(BaseModel):
    """Required regulatory source for a golden case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    section: str = Field(min_length=1)


class GoldenTurn(BaseModel):
    """One turn in a multi-turn golden case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(min_length=1)
    text: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)


class ThresholdExpectation(BaseModel):
    """Boundary metadata required by threshold cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pair_id: str = Field(min_length=1)
    boundary: float
    value: float
    dose_quantity: str = Field(min_length=1)
    side: str = Field(pattern=r"^(below|at|above)$")
    expected_rule_outcome: str = Field(min_length=1)


class RefusalExpectation(BaseModel):
    """Expected refusal behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1)
    forbidden_phrase: str = Field(min_length=1)


class RuleExecution(BaseModel):
    """Execute a case through the existing deterministic R1-R5 adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rule"]
    rule_id: Literal["R1", "R2", "R3", "R4", "R5"]
    inputs: dict[str, Any]


class ReadinessExecution(BaseModel):
    """Execute a case through the deterministic readiness gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["readiness"]
    request_kind: Literal[
        "policy_question",
        "assess",
        "action",
        "out_of_scope",
    ]
    normalized_record_present: bool
    missing_required_fields: tuple[str, ...] = ()
    low_confidence_fields: tuple[str, ...] = ()


class EscalationExecution(BaseModel):
    """Execute a case through the deterministic escalation evaluator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["escalation"]

    fields_below_floor: tuple[str, ...] = ()
    insufficient_data_rules: tuple[str, ...] = ()
    near_boundary_rules: tuple[str, ...] = ()
    reviewer_iterations: int = 0
    reviewer_approved: bool = True
    unresolved_citations: tuple[str, ...] = ()
    retrieval_below_threshold: bool = False
    prompt_attack_fired: bool = False
    notification_required_rules: tuple[str, ...] = ()
    planned_special_exposure_valid: bool = False
    doses_at_or_above_annual_limit: tuple[str, ...] = ()
    photo_contradicts_narrative: bool = False


class RetrievalExecution(BaseModel):
    """Execute a case through the regulatory knowledge-base retriever."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["retrieval"]
    k: int = Field(default=4, ge=1, le=10)
    status: Literal["in_force", "proposed"] | None = None
    expect_found: bool = True


GoldenExecution = RuleExecution | ReadinessExecution | EscalationExecution | RetrievalExecution


class GoldenCase(BaseModel):
    """One version-controlled golden evaluation case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    category: GoldenCategory
    query: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)

    sources: tuple[GoldenSource, ...] = ()
    exposure_id: str | None = None
    why: str = Field(min_length=1)

    threshold: ThresholdExpectation | None = None
    refusal: RefusalExpectation | None = None
    turns: tuple[GoldenTurn, ...] = ()

    required_terms: tuple[str, ...] = ()
    forbidden_sources: tuple[str, ...] = ()
    expected_missing_fields: tuple[str, ...] = ()
    expected_triggers: tuple[str, ...] = ()

    execution: GoldenExecution | None = Field(
        default=None,
        discriminator="kind",
    )

    @model_validator(mode="after")
    def validate_case_specific_fields(self):
        """Validate category-specific golden metadata."""

        if self.category == GoldenCategory.THRESHOLD and self.threshold is None:
            raise ValueError("threshold cases require threshold metadata")

        if self.category == GoldenCategory.REFUSAL and self.refusal is None:
            raise ValueError("refusal cases require refusal metadata")

        if len(self.turns) == 1:
            raise ValueError("multi-turn cases must contain at least two turns")

        return self
