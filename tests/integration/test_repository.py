"""The repository against a real Postgres with pgvector."""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from dosimeter.repository import entitlements, orm, queries, seeds
from dosimeter.repository.migrate import migrate_up, pending
from dosimeter.repository.models import (
    Artifact,
    EntitlementDenial,
    EscalationTrigger,
    Exposure,
    ExtractedField,
    GuardrailEvent,
    HistoricalExposure,
    ModelCall,
    Retrieval,
    ReviewDecision,
    RuleInvocation,
    RunRecord,
    ToolInvocation,
)

DIMENSIONS = orm.EMBEDDING_DIMENSIONS


def embedding(seed: float) -> list[float]:
    return [seed] + [0.0] * (DIMENSIONS - 1)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def new_run(db: Session, **overrides) -> RunRecord:
    record = RunRecord(
        id=uuid4(),
        correlation_id="corr-1",
        command="assess",
        turn_kind="assess",
        **overrides,
    )
    queries.insert_run_record(db, record)
    db.commit()
    return record


def test_migrate_up_is_idempotent(db: Session) -> None:
    assert pending(db) == []
    assert migrate_up(db) == []


def test_vector_extension_is_installed(db: Session) -> None:
    installed = db.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))

    assert installed == "vector"


def test_run_record_and_its_children_write(db: Session) -> None:
    record = new_run(db)

    queries.add_tool_invocation(
        db,
        ToolInvocation(
            run_id=record.id,
            tool_name="find_similar_exposures",
            argument_sha256=sha256("args"),
            outcome="ok",
            duration_ms=12.5,
        ),
    )
    queries.add_rule_invocation(
        db,
        RuleInvocation(
            run_id=record.id,
            rule_id="R1",
            outcome="required",
            threshold_named="20.2202(a)(1)(i)",
            inputs={"tede_rem": 26.0},
        ),
    )
    queries.add_retrieval(
        db,
        Retrieval(
            run_id=record.id,
            query_sha256=sha256("query"),
            chunk_ids=["CFR-20-REPORTS#0007"],
            scores=[0.81],
            status_filter="in_force",
        ),
    )
    queries.add_model_call(
        db,
        ModelCall(
            run_id=record.id,
            model_id="reasoning-model-id",
            role="reasoning",
            input_tokens=900,
            output_tokens=120,
            duration_ms=1500.0,
        ),
    )
    queries.add_escalation_trigger(
        db,
        EscalationTrigger(
            run_id=record.id,
            trigger_name="near_boundary",
            evaluated=True,
            fired=True,
        ),
    )
    queries.add_guardrail_event(
        db,
        GuardrailEvent(run_id=record.id, stage="output", action="blocked", detail={"rule": "R1"}),
    )
    db.commit()

    retrieval = db.scalars(select(orm.RetrievalRow)).one()
    assert retrieval.chunk_ids == ["CFR-20-REPORTS#0007"]
    assert retrieval.scores == [0.81]
    assert db.scalar(select(func.count()).select_from(orm.RuleInvocationRow)) == 1
    assert db.scalars(select(orm.EscalationTriggerRow)).one().fired is True


def test_a_run_record_is_finished_with_its_outcome(db: Session) -> None:
    record = new_run(db)

    queries.finish_run_record(db, record.id, "notification_required")
    db.commit()

    stored = queries.get_run_record(db, record.id)
    assert stored.outcome == "notification_required"
    assert stored.command == "assess"


def test_artifacts_and_extracted_fields_round_trip(db: Session) -> None:
    queries.insert_exposure(
        db,
        Exposure(id="exp-0411", worker_id="WKR-1047", district="District 1"),
    )
    artifact_id = queries.insert_artifact(
        db,
        Artifact(
            exposure_id="exp-0411",
            kind="exposure-report",
            content_sha256=sha256("pdf"),
            s3_bucket="dosimeter-packets",
            s3_key="exp-0411/exposure-report.pdf",
            status="cracked",
        ),
    )
    queries.insert_extracted_fields(
        db,
        [
            ExtractedField(
                exposure_id="exp-0411",
                artifact_id=artifact_id,
                field_key="total_effective_dose_equivalent",
                value="6.2",
                unit="rem",
                confidence=0.99,
                page=1,
            )
        ],
    )
    db.commit()

    fields = queries.list_extracted_fields(db, "exp-0411")
    assert [item.field_key for item in fields] == ["total_effective_dose_equivalent"]
    assert fields[0].confidence == pytest.approx(0.99)
    assert queries.list_artifacts(db, "exp-0411")[0].status == "cracked"


def test_idempotency_key_is_claimed_once(db: Session) -> None:
    assert queries.claim_idempotency_key(db, "key-1", "submit") is True
    db.commit()
    assert queries.claim_idempotency_key(db, "key-1", "submit") is False


def test_review_queue_flow(db: Session) -> None:
    seeds.apply_seeds(db)
    officer = queries.officer_by_code(db, "OFF-101")
    queue_id = queries.enqueue_review(db, "exp-0411", "District 1", "confidence_floor")
    db.commit()

    assert queries.claim_review(db, queue_id, officer.id) is True
    decision_id = queries.record_review_decision(
        db,
        ReviewDecision(
            queue_id=queue_id,
            decision="approved_with_edits",
            original_payload={"outcome": "insufficient_data"},
            edited_payload={"outcome": "insufficient_data", "note": "field re-read by officer"},
            approver_officer_id=officer.id,
        ),
    )
    db.commit()

    assert decision_id > 0
    stored = db.scalars(select(orm.ReviewDecisionRow)).one()
    assert stored.original_payload != stored.edited_payload
    assert db.get(orm.ReviewQueueRow, queue_id).state == "decided"


def test_seeds_give_three_officers_across_three_districts(db: Session) -> None:
    counts = seeds.apply_seeds(db)

    assert counts["officers"] >= 3
    assert len(entitlements.granted_districts(db, "OFF-101")) == 2
    assert entitlements.granted_districts(db, "OFF-102") == ["District 3"]
    assert entitlements.granted_districts(db, "OFF-103") == ["District 4"]


def test_seeds_are_idempotent(db: Session) -> None:
    seeds.apply_seeds(db)
    seeds.apply_seeds(db)

    assert db.scalar(select(func.count()).select_from(orm.OfficerRow)) == 4
    assert db.scalar(select(func.count()).select_from(orm.GrantRow)) == 4


def test_seeds_carry_the_prior_lifetime_planned_exposure_dose(db: Session) -> None:
    seeds.apply_seeds(db)

    history = queries.worker_dose_history(
        db,
        seeds.P4_WORKER_ID,
        "planned_special_exposure_lifetime",
    )

    assert [record.value for record in history] == [6.0]
    assert history[0].unit == "rem"


PERSON_NAME_COLUMNS = {
    "name",
    "full_name",
    "first_name",
    "last_name",
    "worker_name",
    "employee_name",
    "crew_name",
    "officer_name",
}


def test_no_table_in_the_database_has_a_person_name_column(db: Session) -> None:
    inspector = inspect(db.get_bind())

    found = [
        f"{table}.{column['name']}"
        for table in inspector.get_table_names()
        for column in inspector.get_columns(table)
        if column["name"] in PERSON_NAME_COLUMNS
    ]

    assert found == []


def test_an_officer_without_a_grant_gets_a_denial_not_an_empty_list(db: Session) -> None:
    seeds.apply_seeds(db)

    result = entitlements.exposures_for_officer(db, seeds.UNGRANTED_OFFICER)

    assert isinstance(result, EntitlementDenial)
    assert result.reason_code == entitlements.NO_GRANTS
    assert result.officer_code == seeds.UNGRANTED_OFFICER


def test_an_unknown_officer_gets_a_denial(db: Session) -> None:
    seeds.apply_seeds(db)

    result = entitlements.exposures_for_officer(db, "OFF-999")

    assert isinstance(result, EntitlementDenial)
    assert result.reason_code == entitlements.UNKNOWN_OFFICER


def test_one_exposure_is_readable_only_by_its_owning_officer(db: Session) -> None:
    seeds.apply_seeds(db)

    owner = entitlements.exposure_for_officer(db, "OFF-103", "exp-0414")
    outsider = entitlements.exposure_for_officer(db, "OFF-101", "exp-0414")

    assert isinstance(owner, Exposure)
    assert owner.district == "District 4"
    assert isinstance(outsider, EntitlementDenial)
    assert outsider.reason_code == entitlements.DISTRICT_NOT_GRANTED
    assert outsider.district == "District 4"


def test_officer_sees_only_their_own_districts(db: Session) -> None:
    seeds.apply_seeds(db)

    visible = entitlements.exposures_for_officer(db, "OFF-101")

    assert {item.id for item in visible} == {"exp-0411", "exp-0412"}


def test_similar_exposure_search_scores_and_quotes_the_narrative(db: Session) -> None:
    seeds.apply_seeds(db)
    records = [
        (
            "hist-0001",
            "District 1",
            "The source assembly would not retract into the camera. The crew withdrew.",
            embedding(1.0),
        ),
        (
            "hist-0002",
            "District 1",
            "Routine survey found no loss of control. Equipment worked normally.",
            embedding(0.2),
        ),
        (
            "hist-0003",
            "District 4",
            "A retract failure on the same camera model was reported.",
            embedding(1.0),
        ),
    ]
    for exposure_id, district, narrative, vector in records:
        queries.insert_historical_exposure(
            db,
            HistoricalExposure(
                exposure_id=exposure_id,
                worker_id="WKR-1047",
                district=district,
                occurred_on=date(2025, 5, 1),
                outcome="notification_required",
                deciding_rule="R1",
                narrative=narrative,
            ),
            embedding=vector,
        )
    db.commit()

    found = entitlements.similar_exposures_for_officer(
        db,
        "OFF-101",
        embedding(1.0),
        query_text="source assembly would not retract",
    )

    assert [item.exposure_id for item in found] == ["hist-0001", "hist-0002"]
    assert found[0].score == pytest.approx(1.0, abs=1e-6)
    assert found[0].score > found[1].score
    assert "retract" in found[0].narrative_span.text
    assert found[0].narrative_span.end > found[0].narrative_span.start


def test_similar_exposure_search_denies_an_unentitled_officer(db: Session) -> None:
    seeds.apply_seeds(db)

    result = entitlements.similar_exposures_for_officer(
        db,
        seeds.UNGRANTED_OFFICER,
        embedding(1.0),
    )

    assert isinstance(result, EntitlementDenial)
