"""Queue, decision card, the three decisions, and the approval-gated write."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from dosimeter.errors import EntitlementError
from dosimeter.harness.review import (
    Decision,
    queue_entries,
    record_decision,
    write_approved_record,
)
from dosimeter.harness.review_cli import record_from_cli
from dosimeter.harness.run_record import RunRecorder
from dosimeter.repository import Session, orm, queries, seeds

EXPOSURE = "EXP-2026-0412"
OWNER = "OFF-101"
OTHER = "OFF-102"

DOSSIER = {
    "exposure_id": EXPOSURE,
    "outcome": "written_report_required",
    "rule_outcomes": {"R3": "required"},
    "narrative": "The reported dose is above the annual limit.",
    "sources": [{"doc_id": "CFR-20-REPORTS", "chunk_id": "CFR-20-REPORTS#0007", "status": "in_force"}],
}


@pytest.fixture
def queued(db: Session) -> Session:
    seeds.apply_seeds(db)
    officer = queries.officer_by_code(db, OWNER)

    recorder = RunRecorder(
        session=db,
        exposure_id=EXPOSURE,
        officer_id=officer.id,
        command="assess",
    )
    recorder.start()
    queries.save_dossier(db, EXPOSURE, recorder.run_id, DOSSIER)
    recorder.finish("complete")

    queries.enqueue_review(
        db,
        EXPOSURE,
        "District 2",
        "notification_required, dose_at_or_above_annual_limit",
    )
    db.commit()
    return db


def test_queue_lists_the_dossier_with_every_trigger(queued: Session) -> None:
    entries = queue_entries(queued, OWNER)

    assert len(entries) == 1
    assert entries[0].exposure_id == EXPOSURE
    assert entries[0].triggers == [
        "notification_required",
        "dose_at_or_above_annual_limit",
    ]





def test_approving_records_the_decision_and_writes_the_record(queued: Session) -> None:
    printed = record_from_cli(queued, EXPOSURE, OTHER, "approve")

    written = queries.approved_record_for(queued, EXPOSURE)
    decision = queued.scalars(select(orm.ReviewDecisionRow)).one()

    assert "approved" in printed
    assert "nothing was transmitted" in printed
    assert written is not None
    assert written.payload["outcome"] == "written_report_required"
    assert decision.approver_officer_id == queries.officer_by_code(queued, OTHER).id
    assert decision.decided_at is not None


def test_edit_then_approve_stores_the_original_and_the_edit_separately(queued: Session) -> None:
    record_from_cli(queued, EXPOSURE, OTHER, "edit-then-approve", note="Checked by hand.")

    decision = queued.scalars(select(orm.ReviewDecisionRow)).one()

    assert decision.decision == "approved_with_edits"
    assert decision.original_payload["narrative"] == DOSSIER["narrative"]
    assert decision.edited_payload["note"] == "Checked by hand."
    assert decision.original_payload["rule_outcomes"] == decision.edited_payload["rule_outcomes"]




def test_the_approver_may_not_be_the_officer_who_ran_assess(queued: Session) -> None:
    with pytest.raises(EntitlementError):
        record_from_cli(queued, EXPOSURE, OWNER, "approve")

    assert queries.approved_record_for(queued, EXPOSURE) is None



def test_the_same_approval_writes_once_however_often_it_is_retried(queued: Session) -> None:
    officer = queries.officer_by_code(queued, OTHER)
    queue_id = queue_entries(queued, OWNER)[0].queue_id

    decision_id = record_decision(
        session=queued,
        queue_id=queue_id,
        decision=Decision.APPROVED,
        approver_officer_id=officer.id,
        original_payload=DOSSIER,
    )

    first = write_approved_record(queued, EXPOSURE, decision_id, officer.id, DOSSIER)
    second = write_approved_record(queued, EXPOSURE, decision_id, officer.id, DOSSIER)

    assert first.record_id is not None
    assert second.record_id is None
    assert second.already_written
    assert first.idempotency_key == second.idempotency_key
    assert queued.scalar(select(func.count()).select_from(orm.ApprovedRecordRow)) == 1


