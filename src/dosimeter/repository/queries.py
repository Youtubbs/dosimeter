"""Every database read and write in the project, through SQLAlchemy."""

import re
from uuid import UUID

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from dosimeter.repository import orm
from dosimeter.repository.models import (
    ApprovedRecord,
    Artifact,
    DistrictGrant,
    EscalationTrigger,
    Exposure,
    ExtractedField,
    GuardrailEvent,
    HistoricalExposure,
    ModelCall,
    NarrativeSpan,
    Officer,
    Retrieval,
    ReviewDecision,
    ReviewQueueItem,
    RuleInvocation,
    ReviewerVerdictRecord,
    RunRecord,
    SimilarExposure,
    ToolInvocation,
    WorkerDispatch,
    WorkerDoseRecord,
)

_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
_WORD = re.compile(r"[a-z0-9]+")


def ping(session: Session) -> bool:
    """One trivial round trip, for the readiness endpoint."""

    return session.scalar(select(literal(1))) == 1


def upsert_officer(session: Session, officer_code: str) -> Officer:
    row = session.scalars(
        select(orm.OfficerRow).where(orm.OfficerRow.officer_code == officer_code)
    ).first()
    if row is None:
        row = orm.OfficerRow(officer_code=officer_code)
        session.add(row)
        session.flush()
    return Officer(id=row.id, officer_code=row.officer_code)


def officer_by_code(session: Session, officer_code: str) -> Officer | None:
    row = session.scalars(
        select(orm.OfficerRow).where(orm.OfficerRow.officer_code == officer_code)
    ).first()
    return None if row is None else Officer(id=row.id, officer_code=row.officer_code)


def add_grant(session: Session, grant: DistrictGrant) -> None:
    existing = session.scalars(
        select(orm.GrantRow).where(
            orm.GrantRow.officer_id == grant.officer_id,
            orm.GrantRow.district == grant.district,
        )
    ).first()
    if existing is None:
        session.add(orm.GrantRow(officer_id=grant.officer_id, district=grant.district))
        session.flush()


def districts_for_officer(session: Session, officer_code: str) -> list[str]:
    return list(
        session.scalars(
            select(orm.GrantRow.district)
            .join(orm.OfficerRow, orm.OfficerRow.id == orm.GrantRow.officer_id)
            .where(orm.OfficerRow.officer_code == officer_code)
            .order_by(orm.GrantRow.district)
        ).all()
    )


def _exposure(row: orm.ExposureRow) -> Exposure:
    return Exposure(
        id=row.id,
        worker_id=row.worker_id,
        district=row.district,
        occurred_on=row.occurred_on,
        status=row.status,
        narrative=row.narrative,
    )


def insert_exposure(session: Session, exposure: Exposure) -> None:
    row = session.get(orm.ExposureRow, exposure.id)
    if row is None:
        session.add(orm.ExposureRow(**exposure.model_dump()))
    else:
        row.status = exposure.status
    session.flush()


def get_exposure(session: Session, exposure_id: str) -> Exposure | None:
    row = session.get(orm.ExposureRow, exposure_id)
    return None if row is None else _exposure(row)


def insert_artifact(session: Session, artifact: Artifact) -> int:
    row = session.scalars(
        select(orm.ArtifactRow).where(
            orm.ArtifactRow.exposure_id == artifact.exposure_id,
            orm.ArtifactRow.content_sha256 == artifact.content_sha256,
        )
    ).first()
    if row is None:
        row = orm.ArtifactRow(**artifact.model_dump())
        session.add(row)
    else:
        row.status = artifact.status
    session.flush()
    return row.id


def list_artifacts(session: Session, exposure_id: str) -> list[Artifact]:
    rows = session.scalars(
        select(orm.ArtifactRow)
        .where(orm.ArtifactRow.exposure_id == exposure_id)
        .order_by(orm.ArtifactRow.id)
    ).all()
    return [
        Artifact(
            exposure_id=row.exposure_id,
            kind=row.kind,
            content_sha256=row.content_sha256,
            s3_bucket=row.s3_bucket,
            s3_key=row.s3_key,
            status=row.status,
            skipped_reason=row.skipped_reason,
        )
        for row in rows
    ]


def artifact_hashes_by_id(session: Session, exposure_id: str) -> dict[int, str]:
    """Artifact row id to content hash, so a field can name the artifact it came from."""

    rows = session.execute(
        select(orm.ArtifactRow.id, orm.ArtifactRow.content_sha256).where(
            orm.ArtifactRow.exposure_id == exposure_id
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def insert_extracted_fields(session: Session, fields: list[ExtractedField]) -> int:
    if not fields:
        return 0
    session.add_all([orm.ExtractedFieldRow(**item.model_dump()) for item in fields])
    session.flush()
    return len(fields)


def list_extracted_fields(session: Session, exposure_id: str) -> list[ExtractedField]:
    rows = session.scalars(
        select(orm.ExtractedFieldRow)
        .where(orm.ExtractedFieldRow.exposure_id == exposure_id)
        .order_by(orm.ExtractedFieldRow.id)
    ).all()
    return [
        ExtractedField(
            exposure_id=row.exposure_id,
            artifact_id=row.artifact_id,
            field_key=row.field_key,
            value=row.value,
            unit=row.unit,
            confidence=None if row.confidence is None else float(row.confidence),
            page=row.page,
        )
        for row in rows
    ]


def upsert_worker_dose_record(session: Session, record: WorkerDoseRecord) -> None:
    row = session.scalars(
        select(orm.WorkerDoseHistoryRow).where(
            orm.WorkerDoseHistoryRow.worker_id == record.worker_id,
            orm.WorkerDoseHistoryRow.quantity == record.quantity,
            orm.WorkerDoseHistoryRow.as_of == record.as_of,
        )
    ).first()
    if row is None:
        session.add(orm.WorkerDoseHistoryRow(**record.model_dump()))
    else:
        row.value = record.value
    session.flush()


def worker_dose_history(
    session: Session,
    worker_id: str,
    quantity: str | None = None,
) -> list[WorkerDoseRecord]:
    """Prior dose by internal worker id. R4 reads this; it is never logged."""

    statement = select(orm.WorkerDoseHistoryRow).where(
        orm.WorkerDoseHistoryRow.worker_id == worker_id
    )
    if quantity is not None:
        statement = statement.where(orm.WorkerDoseHistoryRow.quantity == quantity)

    rows = session.scalars(statement.order_by(orm.WorkerDoseHistoryRow.as_of)).all()
    return [
        WorkerDoseRecord(
            worker_id=row.worker_id,
            quantity=row.quantity,
            value=float(row.value),
            unit=row.unit,
            as_of=row.as_of,
            note=row.note,
        )
        for row in rows
    ]


def insert_historical_exposure(
    session: Session,
    record: HistoricalExposure,
    embedding: list[float] | None = None,
) -> None:
    row = session.scalars(
        select(orm.HistoricalExposureRow).where(
            orm.HistoricalExposureRow.exposure_id == record.exposure_id
        )
    ).first()
    if row is None:
        session.add(orm.HistoricalExposureRow(**record.model_dump(), embedding=embedding))
    else:
        row.embedding = embedding
    session.flush()


def find_similar_exposures(
    session: Session,
    embedding: list[float],
    districts: list[str],
    query_text: str = "",
    limit: int = 5,
) -> list[SimilarExposure]:
    """Cosine-distance search, scored 1.0 for an exact match and down from there."""

    distance = orm.HistoricalExposureRow.embedding.cosine_distance(embedding)
    rows = session.execute(
        select(orm.HistoricalExposureRow, distance.label("distance"))
        .where(
            orm.HistoricalExposureRow.embedding.is_not(None),
            orm.HistoricalExposureRow.district.in_(districts),
        )
        .order_by(distance)
        .limit(limit)
    ).all()

    return [
        SimilarExposure(
            exposure_id=row.exposure_id,
            district=row.district,
            outcome=row.outcome,
            deciding_rule=row.deciding_rule,
            occurred_on=row.occurred_on,
            score=1.0 - float(distance_value),
            narrative_span=matching_span(row.narrative, query_text),
        )
        for row, distance_value in rows
    ]


def matching_span(narrative: str, query_text: str) -> NarrativeSpan:
    """The sentence of the narrative with the most words in common with the query."""

    wanted = set(_WORD.findall(query_text.lower()))
    best_start, best_end, best_hits = 0, len(narrative), -1

    for match in _SENTENCE.finditer(narrative):
        sentence = match.group().strip()
        if not sentence:
            continue
        hits = len(wanted & set(_WORD.findall(sentence.lower())))
        if hits > best_hits:
            best_hits = hits
            best_start = match.start() + (len(match.group()) - len(match.group().lstrip()))
            best_end = best_start + len(sentence)

    return NarrativeSpan(start=best_start, end=best_end, text=narrative[best_start:best_end])


def enqueue_review(session: Session, exposure_id: str, district: str, reason: str) -> int:
    row = orm.ReviewQueueRow(exposure_id=exposure_id, district=district, reason=reason)
    session.add(row)
    session.flush()
    return row.id


def list_review_queue(session: Session, districts: list[str]) -> list[ReviewQueueItem]:
    rows = session.scalars(
        select(orm.ReviewQueueRow)
        .where(
            orm.ReviewQueueRow.district.in_(districts),
            orm.ReviewQueueRow.state == "waiting",
        )
        .order_by(orm.ReviewQueueRow.created_at, orm.ReviewQueueRow.id)
    ).all()
    return [
        ReviewQueueItem(
            id=row.id,
            exposure_id=row.exposure_id,
            district=row.district,
            reason=row.reason,
            state=row.state,
            claimed_by=row.claimed_by,
        )
        for row in rows
    ]


def claim_review(session: Session, queue_id: int, officer_id: int) -> bool:
    row = session.get(orm.ReviewQueueRow, queue_id)
    if row is None or row.state != "waiting":
        return False

    row.state = "claimed"
    row.claimed_by = officer_id
    row.claimed_at = _now(session)
    session.flush()
    return True


def record_review_decision(session: Session, decision: ReviewDecision) -> int:
    row = orm.ReviewDecisionRow(**decision.model_dump())
    session.add(row)

    queued = session.get(orm.ReviewQueueRow, decision.queue_id)
    if queued is not None:
        queued.state = "decided"

    session.flush()
    return row.id


def _now(session: Session):
    return session.scalar(select(func.now()))


def start_session(
    session: Session,
    session_id: UUID,
    correlation_id: str,
    officer_id: int | None = None,
    exposure_id: str | None = None,
) -> None:
    session.add(
        orm.SessionRow(
            id=session_id,
            correlation_id=correlation_id,
            officer_id=officer_id,
            exposure_id=exposure_id,
        )
    )
    session.flush()


def end_session(session: Session, session_id: UUID) -> None:
    row = session.get(orm.SessionRow, session_id)
    if row is not None:
        row.ended_at = _now(session)
        session.flush()


def insert_run_record(session: Session, record: RunRecord) -> None:
    session.add(orm.RunRecordRow(**record.model_dump()))
    session.flush()


def get_run_record(session: Session, run_id: UUID) -> RunRecord | None:
    row = session.get(orm.RunRecordRow, run_id)
    if row is None:
        return None
    return RunRecord(
        id=row.id,
        correlation_id=row.correlation_id,
        command=row.command,
        turn_kind=row.turn_kind,
        exposure_id=row.exposure_id,
        officer_id=row.officer_id,
        session_id=row.session_id,
        outcome=row.outcome,
        corrects_run_id=row.corrects_run_id,
        token_totals=row.token_totals or {},
        finished_at=row.finished_at,
    )


def set_token_totals(session: Session, run_id: UUID, totals: dict[str, int]) -> None:
    row = session.get(orm.RunRecordRow, run_id)
    if row is not None:
        row.token_totals = dict(totals)
        session.flush()


def finish_run_record(session: Session, run_id: UUID, outcome: str) -> None:
    row = session.get(orm.RunRecordRow, run_id)
    if row is not None:
        row.outcome = outcome
        row.finished_at = _now(session)
        session.flush()


def add_worker_dispatch(session: Session, dispatch: WorkerDispatch) -> None:
    session.add(orm.WorkerDispatchRow(**dispatch.model_dump()))
    session.flush()


def add_reviewer_verdict(session: Session, verdict: ReviewerVerdictRecord) -> None:
    session.add(orm.ReviewerVerdictRow(**verdict.model_dump()))
    session.flush()


def correct_run_record(session: Session, record: RunRecord, corrects: UUID) -> None:
    """A correction is a new row pointing at the original, never an edit."""

    insert_run_record(session, record.model_copy(update={"corrects_run_id": corrects}))


def run_record_detail(session: Session, run_id: UUID) -> dict[str, list]:
    """Everything recorded under one run, for trace and the evaluators."""

    def rows(model, order):
        return list(session.scalars(select(model).where(model.run_id == run_id).order_by(order)).all())

    return {
        "dispatches": rows(orm.WorkerDispatchRow, orm.WorkerDispatchRow.id),
        "tool_invocations": rows(orm.ToolInvocationRow, orm.ToolInvocationRow.id),
        "rule_invocations": rows(orm.RuleInvocationRow, orm.RuleInvocationRow.id),
        "retrievals": rows(orm.RetrievalRow, orm.RetrievalRow.id),
        "model_calls": rows(orm.ModelCallRow, orm.ModelCallRow.id),
        "reviewer_verdicts": rows(orm.ReviewerVerdictRow, orm.ReviewerVerdictRow.iteration),
        "escalation_triggers": rows(orm.EscalationTriggerRow, orm.EscalationTriggerRow.id),
        "guardrail_events": rows(orm.GuardrailEventRow, orm.GuardrailEventRow.id),
    }


def latest_run_record(session: Session, exposure_id: str, command: str | None = None):
    statement = select(orm.RunRecordRow).where(orm.RunRecordRow.exposure_id == exposure_id)
    if command is not None:
        statement = statement.where(orm.RunRecordRow.command == command)
    return session.scalars(statement.order_by(orm.RunRecordRow.started_at.desc())).first()


def save_dossier(session: Session, exposure_id: str, run_id: UUID, payload: dict) -> int:
    row = orm.DossierRow(exposure_id=exposure_id, run_id=run_id, payload=payload)
    session.add(row)
    session.flush()
    return row.id


def latest_dossier(session: Session, exposure_id: str):
    return session.scalars(
        select(orm.DossierRow)
        .where(orm.DossierRow.exposure_id == exposure_id)
        .order_by(orm.DossierRow.created_at.desc(), orm.DossierRow.id.desc())
    ).first()


def write_approved_record(session: Session, record: ApprovedRecord) -> int | None:
    """
    The harness-only write. Returns the row id, or None when this key has
    already been written, so a retry with the same key writes once.
    """

    existing = session.scalars(
        select(orm.ApprovedRecordRow).where(
            orm.ApprovedRecordRow.idempotency_key == record.idempotency_key
        )
    ).first()
    if existing is not None:
        return None

    row = orm.ApprovedRecordRow(**record.model_dump())
    session.add(row)
    session.flush()
    return row.id


def approved_record_for(session: Session, exposure_id: str):
    return session.scalars(
        select(orm.ApprovedRecordRow)
        .where(orm.ApprovedRecordRow.exposure_id == exposure_id)
        .order_by(orm.ApprovedRecordRow.written_at.desc())
    ).first()


def review_decision(session: Session, decision_id: int):
    return session.get(orm.ReviewDecisionRow, decision_id)


def add_tool_invocation(session: Session, invocation: ToolInvocation) -> None:
    session.add(orm.ToolInvocationRow(**invocation.model_dump()))
    session.flush()


def add_rule_invocation(session: Session, invocation: RuleInvocation) -> None:
    session.add(orm.RuleInvocationRow(**invocation.model_dump()))
    session.flush()


def add_retrieval(session: Session, retrieval: Retrieval) -> None:
    session.add(orm.RetrievalRow(**retrieval.model_dump()))
    session.flush()


def add_model_call(session: Session, call: ModelCall) -> None:
    session.add(orm.ModelCallRow(**call.model_dump()))
    session.flush()


def add_escalation_trigger(session: Session, trigger: EscalationTrigger) -> None:
    session.add(orm.EscalationTriggerRow(**trigger.model_dump()))
    session.flush()


def add_guardrail_event(session: Session, event: GuardrailEvent) -> None:
    session.add(orm.GuardrailEventRow(**event.model_dump()))
    session.flush()


def save_ingestion_report(
    session: Session,
    exposure_id: str,
    artifacts_processed: int,
    artifacts_skipped: int,
    fields_extracted: int,
    low_confidence_fields: list[dict],
    failures: list[dict],
) -> int:
    row = orm.IngestionReportRow(
        exposure_id=exposure_id,
        artifacts_processed=artifacts_processed,
        artifacts_skipped=artifacts_skipped,
        fields_extracted=fields_extracted,
        low_confidence_fields=low_confidence_fields,
        failures=failures,
    )
    session.add(row)
    session.flush()
    return row.id


def latest_ingestion_report(session: Session, exposure_id: str) -> orm.IngestionReportRow | None:
    return session.scalars(
        select(orm.IngestionReportRow)
        .where(orm.IngestionReportRow.exposure_id == exposure_id)
        .order_by(orm.IngestionReportRow.created_at.desc(), orm.IngestionReportRow.id.desc())
    ).first()


def delete_extracted_fields(session: Session, exposure_id: str) -> None:
    """Clear the fields for one exposure so a re-run does not double them."""

    for row in session.scalars(
        select(orm.ExtractedFieldRow).where(orm.ExtractedFieldRow.exposure_id == exposure_id)
    ).all():
        session.delete(row)
    session.flush()


def claim_idempotency_key(
    session: Session,
    key: str,
    scope: str,
    result_ref: str | None = None,
) -> bool:
    """True the first time this key is claimed, False every time after."""

    if session.get(orm.IdempotencyKeyRow, key) is not None:
        return False

    session.add(orm.IdempotencyKeyRow(key=key, scope=scope, result_ref=result_ref))
    session.flush()
    return True
