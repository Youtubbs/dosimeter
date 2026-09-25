"""
The Eligibility Check: what happens after the Reviewer approves.

It runs the deterministic evaluator over the signals the turn recorded, writes
every trigger it looked at to the run record, and queues the dossier when any
of them fired. A dossier with no fired trigger stands.
"""

from __future__ import annotations

from dataclasses import dataclass

from dosimeter.harness.escalation import Evaluator, EscalationOutcome, TriggerSignals
from dosimeter.harness.run_record import RunRecorder
from dosimeter.logging_config import get_logger
from dosimeter.repository import Session, queries

_LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class EligibilityResult:
    outcome: EscalationOutcome
    queue_id: int | None

    @property
    def escalated(self) -> bool:
        return self.queue_id is not None


def check_eligibility(
    session: Session,
    exposure_id: str,
    district: str,
    signals: TriggerSignals,
    evaluate: Evaluator,
    recorder: RunRecorder | None = None,
) -> EligibilityResult:
    """Evaluate, record, and queue when anything fired."""

    outcome = evaluate(signals)

    if recorder is not None:
        fired = {item.trigger: item.detail for item in outcome.fired}
        for trigger in outcome.evaluated:
            recorder.trigger_evaluated(
                trigger.value,
                fired=trigger in fired,
                detail=fired.get(trigger) or None,
            )

    if not outcome.escalates:
        _LOGGER.info("eligibility.clear", extra={"exposure_id": exposure_id})
        return EligibilityResult(outcome=outcome, queue_id=None)

    queue_id = queries.enqueue_review(session, exposure_id, district, outcome.reason())
    session.commit()

    _LOGGER.info(
        "eligibility.escalated",
        extra={"exposure_id": exposure_id, "queue_id": queue_id, "triggers": outcome.names()},
    )
    return EligibilityResult(outcome=outcome, queue_id=queue_id)


def eligibility_node(
    session: Session,
    evaluate: Evaluator,
    signals_from_state,
    district: str,
    recorder: RunRecorder | None = None,
):
    """The graph node. Reads the turn's signals from state, never from a model."""

    def run(state) -> dict:
        subject = state["subject"]
        result = check_eligibility(
            session=session,
            exposure_id=subject.exposure_id,
            district=district,
            signals=signals_from_state(state),
            evaluate=evaluate,
            recorder=recorder,
        )

        return {
            "outcome": "escalated" if result.escalated else "ready_for_officer",
            "escalation_signals": result.outcome.names(),
        }

    return run
