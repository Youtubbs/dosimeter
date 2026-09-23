"""R5 — extraction-confidence and missing-regulatory-data guard."""

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource
# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------
# This is a pipeline parameter, NOT a regulatory threshold.
DEFAULT_CONFIDENCE_FLOOR = 0.60

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------
class ExtractedFieldConfidence(BaseModel):
    """Confidence associated with one extracted packet field."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    field_name: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class R5Inputs(BaseModel):
    """Inputs used by the R5 confidence/readiness rule."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    fields: tuple[ExtractedFieldConfidence, ...]

    requires_appendix_c: bool = False


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
R5_SOURCE = RuleSource(
    citation="Pipeline confidence policy",
    section="Extraction confidence guard",
    status="in_force",
)

LOST_MATERIAL_SOURCE = RuleSource(
    citation="10 CFR 20.2201",
    section="Reports of theft or loss of licensed material",
    status="in_force",
)


# ---------------------------------------------------------------------------
# R5
# ---------------------------------------------------------------------------
def evaluate_r5(
    inputs: R5Inputs,
    *,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
) -> RuleResult:
    """Evaluate extraction confidence and regulatory-data readiness."""

    inputs_used = inputs.model_dump()

    # ------------------------------------------------------------------
    # Appendix C path
    #
    # Appendix C quantities are deliberately absent from the project
    # corpus. Never invent or hardcode those values.
    # ------------------------------------------------------------------
    if inputs.requires_appendix_c:
        return RuleResult(
            rule_id="R5",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(LOST_MATERIAL_SOURCE,),
            inputs_used=inputs_used,
            threshold={
                "required_reference": "Appendix C to Part 20",
            },
            explanation=(
                "The determination cannot be completed because the "
                "applicable lost-material threshold depends on Appendix C "
                "to Part 20, which is not available in the project corpus."
            ),
            missing_fields=("Appendix C to Part 20",),
        )

    # ------------------------------------------------------------------
    # Confidence check
    #
    # IMPORTANT:
    # exactly 0.60 passes when the floor is 0.60.
    #
    # Only values strictly BELOW the floor require human determination.
    # ------------------------------------------------------------------
    low_confidence_fields = tuple(
        field.field_name
        for field in inputs.fields
        if field.confidence < confidence_floor
    )

    if low_confidence_fields:
        return RuleResult(
            rule_id="R5",
            outcome=RuleOutcome.HUMAN_DETERMINATION,
            sources=(R5_SOURCE,),
            inputs_used=inputs_used,
            threshold={
                "confidence_floor": confidence_floor,
            },
            explanation=(
                "Human determination is required because one or more "
                "extracted fields are below the configured confidence floor."
            ),
            failing_conditions=low_confidence_fields,
        )

    # ------------------------------------------------------------------
    # All extracted fields satisfy the configured confidence floor.
    # ------------------------------------------------------------------
    return RuleResult(
        rule_id="R5",
        outcome=RuleOutcome.PASS,
        sources=(R5_SOURCE,),
        inputs_used=inputs_used,
        threshold={
            "confidence_floor": confidence_floor,
        },
        explanation=(
            "All extracted fields meet or exceed the configured "
            "confidence floor."
        ),
    )
