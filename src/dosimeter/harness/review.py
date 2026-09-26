"""
The officer decision path: approve, edit then approve, or reject.

An edit changes the narrative, never the determination. The write that follows
an approval is harness only, needs a recorded approval, and transmits nothing.
"""

import hashlib
import json
import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.decorators import retry
from dosimeter.errors import EntitlementError, ExternalServiceError, GateError
from dosimeter.repository import Session, entitlements, queries
from dosimeter.repository.models import ApprovedRecord, EntitlementDenial, ReviewDecision

logger = logging.getLogger(__name__)

# Nothing under these keys may change in an edit.
DETERMINATION_KEYS = (
    "rule_outcomes",
    "rule_invocations",
    "doses",
    "dose_quantities",
    "sources",
    "outcome",
    "thresholds",
)

# The only keys an edit may add: the wording and a note.
EDITABLE_KEYS = ("narrative", "note")


class Decision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"


class EditRejection(BaseModel):
    """Why an edit was refused. The officer rejects instead of rewriting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason_code: str
    message: str
    field_path: str


def _source_index(payload: dict[str, Any]) -> dict[str, str]:
    """chunk id to doc id, so a repoint can be checked against the same source."""

    index: dict[str, str] = {}
    for source in payload.get("sources", []) or []:
        chunk_id = source.get("chunk_id")
        if chunk_id:
            index[chunk_id] = source.get("doc_id", "")
    return index


def validate_edit(original: dict[str, Any], edited: dict[str, Any]) -> EditRejection | None:
    """None when the edit is narrative only, otherwise why it is refused."""

    for key in DETERMINATION_KEYS:
        if key == "sources":
            continue
        if original.get(key) != edited.get(key):
            return EditRejection(
                reason_code="determination_changed",
                message="an edit may change wording, not a determination",
                field_path=key,
            )

    original_sources = original.get("sources", []) or []
    edited_sources = edited.get("sources", []) or []

    if len(original_sources) != len(edited_sources):
        return EditRejection(
            reason_code="sources_changed",
            message="an edit may repoint a citation, not add or remove one",
            field_path="sources",
        )

    for index, (was, now) in enumerate(zip(original_sources, edited_sources, strict=True)):
        if was.get("doc_id") != now.get("doc_id"):
            return EditRejection(
                reason_code="cited_document_changed",
                message="a citation may be repointed within the same source only",
                field_path=f"sources[{index}].doc_id",
            )
        if was.get("status") != now.get("status"):
            return EditRejection(
                reason_code="source_status_changed",
                message="the status of a source is not editable",
                field_path=f"sources[{index}].status",
            )

    unexpected = [
        key
        for key in edited
        if key not in original and key not in EDITABLE_KEYS
    ]
    if unexpected:
        return EditRejection(
            reason_code="unexpected_field",
            message="an edit may not add fields to the dossier",
            field_path=unexpected[0],
        )

    return None


def idempotency_key_for(exposure_id: str, decision_id: int, payload: dict[str, Any]) -> str:
    """Same approval, same key, however many times the write is retried."""

    material = json.dumps(
        {"exposure_id": exposure_id, "decision_id": decision_id, "payload": payload},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ApprovalWrite(BaseModel):
    """The result of the write that follows an approval."""

    model_config = ConfigDict(frozen=True)

    decision_id: int
    idempotency_key: str
    record_id: int | None
    already_written: bool


def record_decision(
    session: Session,
    queue_id: int,
    decision: Decision,
    approver_officer_id: int,
    original_payload: dict[str, Any],
    edited_payload: dict[str, Any] | None = None,
    assessed_by_officer_id: int | None = None,
    enforce_two_person: bool = True,
) -> int:
    """
    Record what the officer decided. The approver must not be the officer who
    ran the assessment.
    """

    if (
        enforce_two_person
        and assessed_by_officer_id is not None
        and assessed_by_officer_id == approver_officer_id
    ):
        raise EntitlementError(
            "the approver must be a different officer from the one who ran assess",
            officer_id=approver_officer_id,
        )

    if decision is Decision.APPROVED_WITH_EDITS:
        if edited_payload is None:
            raise GateError("an edit-then-approve needs an edited payload")

        rejection = validate_edit(original_payload, edited_payload)
        if rejection is not None:
            raise GateError(
                rejection.message,
                reason_code=rejection.reason_code,
                field_path=rejection.field_path,
            )

    decision_id = queries.record_review_decision(
        session,
        ReviewDecision(
            queue_id=queue_id,
            decision=decision.value,
            original_payload=original_payload,
            edited_payload=edited_payload,
            approver_officer_id=approver_officer_id,
        ),
    )
    session.commit()

    logger.info(
        "review.decided",
        extra={"queue_id": queue_id, "decision": decision.value, "decision_id": decision_id},
    )
    return decision_id


def write_approved_record(
    session: Session,
    exposure_id: str,
    decision_id: int,
    approver_officer_id: int,
    payload: dict[str, Any],
    attempts: int = 3,
) -> ApprovalWrite:
    """
    The write layer. Harness only, gated on a recorded approval, idempotent on
    the key, and it transmits nothing to anybody.
    """

    decision = queries.review_decision(session, decision_id)
    if decision is None:
        raise GateError("no such decision", decision_id=decision_id)
    if decision.decision not in (Decision.APPROVED.value, Decision.APPROVED_WITH_EDITS.value):
        raise GateError(
            "the record is written only after a recorded approval",
            decision=decision.decision,
        )

    key = idempotency_key_for(exposure_id, decision_id, payload)

    # every try uses the same key, so a retry after a failed commit still writes once
    @retry(attempts=attempts)
    def write_once() -> int | None:
        try:
            record_id = queries.write_approved_record(
                session,
                ApprovedRecord(
                    exposure_id=exposure_id,
                    decision_id=decision_id,
                    idempotency_key=key,
                    payload=payload,
                    approver_officer_id=approver_officer_id,
                ),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return record_id

    try:
        record_id = write_once()
    except Exception as error:
        raise ExternalServiceError(
            "the approved record could not be written",
            exposure_id=exposure_id,
            attempts=attempts,
            detail=str(error),
        ) from error

    return ApprovalWrite(
        decision_id=decision_id,
        idempotency_key=key,
        record_id=record_id,
        already_written=record_id is None,
    )


class QueueEntry(BaseModel):
    """One row of what queue prints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    queue_id: int
    exposure_id: str
    district: str
    triggers: list[str] = Field(default_factory=list)
    state: str


def queue_entries(session: Session, officer_code: str) -> list[QueueEntry] | EntitlementDenial:
    """The waiting dossiers this officer may see, with every trigger named."""

    items = entitlements.review_queue_for_officer(session, officer_code)
    if not isinstance(items, list):
        return items

    return [
        QueueEntry(
            queue_id=item.id,
            exposure_id=item.exposure_id,
            district=item.district,
            triggers=[part.strip() for part in item.reason.split(",") if part.strip()],
            state=item.state,
        )
        for item in items
    ]
