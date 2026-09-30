"""Models for the deterministic golden evaluation set."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GoldenCategory(StrEnum):
    """Supported golden-set evaluation categories."""

    RULE_BOUNDARY = "rule_boundary"
    MISSING_DATA = "missing_data"
    DOSE_QUANTITY = "dose_quantity"
    PACKET = "packet"
    POLICY_QUESTION = "policy_question"
    REFUSAL = "refusal"
    ADVERSARIAL = "adversarial"
    MULTI_TURN = "multi_turn"
    SOURCE_GROUNDING = "source_grounding"
    ESCALATION = "escalation"


class GoldenExpected(BaseModel):
    """Expected deterministic behavior for a golden case."""

    model_config = ConfigDict(extra="forbid")

    outcome: str
    rule_id: str | None = None
    dispatch_workers: bool | None = None
    human_determination_required: bool = False
    escalation_required: bool = False
    required_sources: tuple[str, ...] = ()
    expected_missing_fields: tuple[str, ...] = ()
    expected_triggers: tuple[str, ...] = ()


class GoldenTurn(BaseModel):
    """One user turn in a golden evaluation case."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class GoldenCase(BaseModel):
    """One machine-readable golden evaluation case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: GoldenCategory
    description: str = Field(min_length=1)

    turns: tuple[GoldenTurn, ...] = Field(min_length=1)

    packet_id: str | None = None
    tags: tuple[str, ...] = ()

    expected: GoldenExpected
