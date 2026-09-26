"""What the review command shows and what it records."""

from typing import Any

from dosimeter.errors import EntitlementError, GateError
from dosimeter.harness.review import (
    Decision,
    record_decision,
    write_approved_record,
)
from dosimeter.repository import Session, entitlements, queries
from dosimeter.repository.models import EntitlementDenial

DISCLOSURE = (
    "This dossier is AI generated and must be verified by the officer. "
    "The exposure data is synthetic."
)


def _queue_row_for(session: Session, exposure_id: str, officer_code: str):
    items = entitlements.review_queue_for_officer(session, officer_code)
    if isinstance(items, EntitlementDenial):
        return items
    for item in items:
        if item.exposure_id == exposure_id:
            return item
    return None


def render_decision_card(session: Session, exposure_id: str, officer_code: str) -> str:
    """The card: what escalated it, and the three things the officer may do."""

    row = _queue_row_for(session, exposure_id, officer_code)
    if isinstance(row, EntitlementDenial):
        raise EntitlementError(row.message, reason_code=row.reason_code)
    if row is None:
        return f"{exposure_id} is not waiting for review"

    triggers = [part.strip() for part in row.reason.split(",") if part.strip()]
    dossier = queries.latest_dossier(session, exposure_id)

    lines = [
        f"{exposure_id} (queue {row.id}, {row.district})",
        "",
        "escalated because:",
        *[f"  {trigger}" for trigger in triggers],
        "",
        "decisions:",
        "  approve            record approval as it stands",
        "  edit-then-approve  change wording or add a note, never a determination",
        "  reject             send it back rather than rewriting it",
        "",
        DISCLOSURE,
    ]
    if dossier is None:
        lines.insert(2, "no dossier stored for this exposure yet")

    return "\n".join(lines)


def record_from_cli(
    session: Session,
    exposure_id: str,
    officer_code: str,
    decision: str,
    note: str | None = None,
) -> str:
    """Record the decision, and write the approved record when it is approved."""

    row = _queue_row_for(session, exposure_id, officer_code)
    if isinstance(row, EntitlementDenial):
        raise EntitlementError(row.message, reason_code=row.reason_code)
    if row is None:
        raise GateError("that exposure is not waiting for review", exposure_id=exposure_id)

    officer = queries.officer_by_code(session, officer_code)
    if officer is None:
        raise EntitlementError("no officer with that code", officer_code=officer_code)

    stored = queries.latest_dossier(session, exposure_id)
    original: dict[str, Any] = stored.payload if stored is not None else {"exposure_id": exposure_id}

    run = queries.latest_run_record(session, exposure_id, command="assess")
    assessed_by = run.officer_id if run is not None else None

    chosen = {
        "approve": Decision.APPROVED,
        "edit-then-approve": Decision.APPROVED_WITH_EDITS,
        "reject": Decision.REJECTED,
    }[decision]

    edited = None
    if chosen is Decision.APPROVED_WITH_EDITS:
        edited = dict(original)
        edited["note"] = note or ""

    decision_id = record_decision(
        session=session,
        queue_id=row.id,
        decision=chosen,
        approver_officer_id=officer.id,
        original_payload=original,
        edited_payload=edited,
        assessed_by_officer_id=assessed_by,
    )

    if chosen is Decision.REJECTED:
        return f"{exposure_id} rejected and recorded (decision {decision_id})"

    write = write_approved_record(
        session=session,
        exposure_id=exposure_id,
        decision_id=decision_id,
        approver_officer_id=officer.id,
        payload=edited or original,
    )

    lines = [
        f"{exposure_id} {chosen.value} and recorded (decision {decision_id})",
        f"idempotency key: {write.idempotency_key[:16]}",
        "written already, nothing to do" if write.already_written else "approved record written",
        "nothing was transmitted to anyone",
    ]
    return "\n".join(lines)
