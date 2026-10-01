"""
What happens after the graph's eligibility check decides.

Every trigger it looked at goes on the run record, and the dossier is queued
for a person when any of them fired. A dossier with no fired trigger stands.
"""

import logging

from pydantic import BaseModel

from dosimeter.harness.escalation import EscalationOutcome
from dosimeter.harness.run_record import RunRecorder
from dosimeter.repository import Session, queries

logger = logging.getLogger(__name__)


class EligibilityResult(BaseModel):
    outcome: EscalationOutcome
    queue_id: int | None = None

    @property
    def escalated(self) -> bool:
        return self.queue_id is not None


def record_eligibility(
    session: Session,
    exposure_id: str,
    district: str,
    outcome: EscalationOutcome,
    recorder: RunRecorder | None = None,
) -> EligibilityResult:
    """Record every trigger that was evaluated, and queue the dossier when any fired."""

    if recorder is not None:
        fired = {item.trigger: item.detail for item in outcome.fired}
        for trigger in outcome.evaluated:
            recorder.trigger_evaluated(
                trigger.value,
                fired=trigger in fired,
                detail=fired.get(trigger) or None,
            )

    if not outcome.escalates:
        logger.info("eligibility.clear", extra={"exposure_id": exposure_id})
        return EligibilityResult(outcome=outcome)

    queue_id = queries.enqueue_review(session, exposure_id, district, outcome.reason())
    session.commit()

    logger.info(
        "eligibility.escalated",
        extra={"exposure_id": exposure_id, "queue_id": queue_id, "triggers": outcome.names()},
    )
    return EligibilityResult(outcome=outcome, queue_id=queue_id)
