"""
The models the tool API speaks and the tools call it with. One definition, so
the OpenAPI document and the tool schemas cannot drift apart.
"""

from pydantic import BaseModel, ConfigDict, Field

STRICT = ConfigDict(extra="forbid", frozen=True)


class GetExposureExtractionInput(BaseModel):
    """Takes no arguments. The exposure comes from the session, never from the model."""

    model_config = STRICT


class ExtractionField(BaseModel):
    model_config = STRICT

    field_key: str = Field(description="The field name as it was read off the form.")
    value: str | None = Field(default=None, description="The value as read, never inferred.")
    unit: str | None = Field(default=None, description="The unit printed beside the value.")
    confidence: float | None = Field(default=None, description="Textract confidence, 0 to 1.")
    page: int | None = Field(default=None, description="Page the field was read from.")
    artifact_sha256: str | None = Field(
        default=None,
        description="Content hash of the artifact this field was read from.",
    )


class ExposureExtraction(BaseModel):
    model_config = STRICT

    exposure_id: str
    district: str
    status: str
    fields: list[ExtractionField] = Field(default_factory=list)
    low_confidence_field_keys: list[str] = Field(default_factory=list)


class FindSimilarExposuresInput(BaseModel):
    """Arguments a model may choose when looking for precedent."""

    model_config = STRICT

    query_text: str = Field(
        min_length=3,
        description="What to look for, in the words of the narrative.",
    )
    limit: int = Field(default=5, ge=1, le=20, description="How many candidates to return.")


class SimilarExposureCandidate(BaseModel):
    """A candidate, never a conclusion."""

    model_config = STRICT

    exposure_id: str
    outcome: str = Field(description="The outcome the earlier case was closed with.")
    deciding_rule: str = Field(description="The rule that decided it.")
    score: float = Field(description="Similarity, 1.0 being an exact match.")
    narrative_span: str = Field(description="The part of the narrative that matched.")


class SimilarExposures(BaseModel):
    model_config = STRICT

    candidates: list[SimilarExposureCandidate] = Field(default_factory=list)


class Denial(BaseModel):
    """What an unentitled call gets back. Never an empty result set."""

    model_config = STRICT

    reason_code: str
    message: str
    officer_code: str
    district: str | None = None


class HealthStatus(BaseModel):
    model_config = STRICT

    status: str
    checks: dict[str, str] = Field(default_factory=dict)
