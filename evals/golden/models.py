"""Models for the deterministic golden evaluation set."""

from enum import StrEnum

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
    """A document and section/path required to support the expected result."""

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
    """Extra assertions required for a threshold-boundary case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pair_id: str = Field(min_length=1)
    boundary: float
    value: float
    dose_quantity: str = Field(min_length=1)
    side: str = Field(pattern=r"^(below|at|above)$")
    expected_rule_outcome: str = Field(min_length=1)


class RefusalExpectation(BaseModel):
    """Extra assertions required for an out-of-corpus refusal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1)
    forbidden_phrase: str = Field(min_length=1)


class GoldenCase(BaseModel):
    """One machine-readable golden evaluation case."""

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

    @model_validator(mode="after")
    def validate_case_specific_fields(self):
        """Require metadata that is mandatory for specialized case types."""

        if self.category == GoldenCategory.THRESHOLD and self.threshold is None:
            raise ValueError("threshold cases require threshold metadata")

        if self.category == GoldenCategory.REFUSAL and self.refusal is None:
            raise ValueError("refusal cases require refusal metadata")

        if len(self.turns) == 1:
            raise ValueError("multi-turn cases must contain at least two turns")

        return self
