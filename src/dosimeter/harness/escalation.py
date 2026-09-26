"""
The signals escalation is decided from, and the evaluator that decides it.

The signal model has no field for a model's self-reported confidence, on
purpose: eligibility is computed from what the turn recorded, and a model
saying it feels sure is not evidence.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

STRICT = ConfigDict(extra="forbid", frozen=True)


class Trigger(StrEnum):
    """The eleven named triggers. Each one is recorded by name when it fires."""

    FIELD_BELOW_FLOOR = "field_below_confidence_floor"
    INSUFFICIENT_DATA = "rule_insufficient_data"
    NEAR_BOUNDARY = "value_within_near_boundary_margin"
    REVIEWER_NOT_APPROVED = "reviewer_not_approved_first_time"
    CITATION_FAILED = "citation_failed_to_resolve_or_support"
    RETRIEVAL_BELOW_THRESHOLD = "retrieval_below_similarity_threshold"
    PROMPT_ATTACK_FIRED = "prompt_attack_filter_fired"
    NOTIFICATION_REQUIRED = "notification_required"
    PLANNED_SPECIAL_EXPOSURE_VALID = "planned_special_exposure_valid"
    AT_OR_ABOVE_ANNUAL_LIMIT = "dose_at_or_above_annual_limit"
    PHOTO_CONTRADICTS_NARRATIVE = "photo_contradicts_narrative"


class TriggerSignals(BaseModel):
    """What the turn recorded. There is no self-reported confidence here."""

    model_config = STRICT

    fields_below_floor: list[str] = Field(default_factory=list)
    insufficient_data_rules: list[str] = Field(default_factory=list)
    near_boundary_rules: list[str] = Field(default_factory=list)
    reviewer_iterations: int = 0
    reviewer_approved: bool = True
    unresolved_citations: list[str] = Field(default_factory=list)
    retrieval_below_threshold: bool = False
    prompt_attack_fired: bool = False
    notification_required_rules: list[str] = Field(default_factory=list)
    planned_special_exposure_valid: bool = False
    doses_at_or_above_annual_limit: list[str] = Field(default_factory=list)
    photo_contradicts_narrative: bool = False


class FiredTrigger(BaseModel):
    model_config = STRICT

    trigger: Trigger
    detail: str = ""


class EscalationOutcome(BaseModel):
    """Every trigger that was looked at, and the ones that fired."""

    model_config = STRICT

    evaluated: list[Trigger] = Field(default_factory=list)
    fired: list[FiredTrigger] = Field(default_factory=list)

    @property
    def escalates(self) -> bool:
        return bool(self.fired)

    def names(self) -> list[str]:
        return [item.trigger.value for item in self.fired]

    def reason(self) -> str:
        return ", ".join(self.names()) if self.fired else "no trigger fired"


def evaluate(signals: TriggerSignals) -> EscalationOutcome:
    """
    Stands in until the trigger logic is written. It fires nothing, which is
    visible in the run record as a turn where no trigger was evaluated.
    """

    return EscalationOutcome()
