"""Rows in and rows out. Anything parsed from outside the process forbids extras."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

STRICT = ConfigDict(extra="forbid", frozen=True)


class Officer(BaseModel):
    model_config = STRICT

    id: int
    officer_code: str = Field(min_length=1)


class DistrictGrant(BaseModel):
    model_config = STRICT

    officer_id: int
    district: str = Field(min_length=1)


class EntitlementDenial(BaseModel):
    """What an unentitled call gets back. Never an empty list."""

    model_config = STRICT

    reason_code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    officer_code: str = Field(min_length=1)
    district: str | None = None


class Exposure(BaseModel):
    model_config = STRICT

    id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    district: str = Field(min_length=1)
    occurred_on: date | None = None
    status: str = "received"
    narrative: str | None = None


class Artifact(BaseModel):
    model_config = STRICT

    exposure_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    s3_bucket: str = Field(min_length=1)
    s3_key: str = Field(min_length=1)
    status: str = "pending"
    skipped_reason: str | None = None


class ExtractedField(BaseModel):
    model_config = STRICT

    exposure_id: str = Field(min_length=1)
    artifact_id: int
    field_key: str = Field(min_length=1)
    value: str | None = None
    unit: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    page: int | None = None


class WorkerDoseRecord(BaseModel):
    """Keyed by internal worker id. There is no name here and no name column."""

    model_config = STRICT

    worker_id: str = Field(min_length=1)
    quantity: str = Field(min_length=1)
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)
    as_of: date
    note: str | None = None


class HistoricalExposure(BaseModel):
    model_config = STRICT

    exposure_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    district: str = Field(min_length=1)
    occurred_on: date
    outcome: str = Field(min_length=1)
    deciding_rule: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    normalized_fields: dict[str, str] = Field(default_factory=dict)


class NarrativeSpan(BaseModel):
    model_config = STRICT

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str


class SimilarExposure(BaseModel):
    model_config = STRICT

    exposure_id: str
    district: str
    outcome: str
    deciding_rule: str
    occurred_on: date
    score: float
    narrative_span: NarrativeSpan


class ReviewQueueItem(BaseModel):
    model_config = STRICT

    id: int
    exposure_id: str
    district: str
    reason: str
    state: str
    claimed_by: int | None = None


class ReviewDecision(BaseModel):
    model_config = STRICT

    queue_id: int
    decision: str = Field(min_length=1)
    original_payload: dict
    edited_payload: dict | None = None
    approver_officer_id: int


class RunRecord(BaseModel):
    model_config = STRICT

    id: UUID
    correlation_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    turn_kind: str = Field(min_length=1)
    exposure_id: str | None = None
    officer_id: int | None = None
    outcome: str | None = None
    finished_at: datetime | None = None


class ToolInvocation(BaseModel):
    model_config = STRICT

    run_id: UUID
    tool_name: str
    argument_sha256: str = Field(min_length=64, max_length=64)
    outcome: str
    duration_ms: float | None = None


class RuleInvocation(BaseModel):
    model_config = STRICT

    run_id: UUID
    rule_id: str
    outcome: str
    threshold_named: str | None = None
    inputs: dict = Field(default_factory=dict)


class Retrieval(BaseModel):
    model_config = STRICT

    run_id: UUID
    query_sha256: str = Field(min_length=64, max_length=64)
    chunk_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    status_filter: str | None = None


class ModelCall(BaseModel):
    model_config = STRICT

    run_id: UUID
    model_id: str
    role: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: float | None = None


class EscalationTrigger(BaseModel):
    model_config = STRICT

    run_id: UUID
    trigger_name: str
    evaluated: bool = False
    fired: bool = False
    detail: str | None = None


class GuardrailEvent(BaseModel):
    model_config = STRICT

    run_id: UUID
    stage: str
    action: str
    guardrail_id: str | None = None
    detail: dict = Field(default_factory=dict)
