"""
One assess turn: build the graph, run it on its own thread, record what it did,
record the eligibility check, and store the dossier.
"""

import logging
import time
from uuid import UUID, uuid4

from pydantic import BaseModel

from dosimeter.config.settings import Settings
from dosimeter.errors import EntitlementError, GateError
from dosimeter.graph.checkpointer import open_checkpointer
from dosimeter.graph.graph import build_graph
from dosimeter.graph.schemas import Subject
from dosimeter.graph.state import initial_state
from dosimeter.graph.threads import Participant, thread_config
from dosimeter.harness.eligibility import EligibilityResult, record_eligibility
from dosimeter.harness.escalation import EscalationOutcome
from dosimeter.harness.run_record import RunRecorder
from dosimeter.repository import Session, queries

logger = logging.getLogger(__name__)


class AssessResult(BaseModel):
    exposure_id: str
    run_id: UUID
    outcome: str
    dossier_id: int
    duration_seconds: float
    eligibility: EligibilityResult

    @property
    def escalated(self) -> bool:
        return self.eligibility.escalated


def dossier_payload(state: dict, exposure_id: str) -> dict:
    """What is stored for the renderer to read back cold."""

    proposals = state.get("proposals") or {}
    escalation = state.get("escalation")
    return {
        "exposure_id": exposure_id,
        "outcome": state.get("outcome"),
        "workers": sorted(proposals),
        "proposals": {name: item.model_dump(mode="json") for name, item in proposals.items()},
        "rule_invocations": state.get("rule_invocations") or [],
        "sources": state.get("retrieval_log") or [],
        "escalation_signals": escalation.names() if escalation else [],
        "reviewer_verdicts": [
            item.model_dump(mode="json") for item in state.get("reviewer_verdicts") or []
        ],
    }


def run_assess(
    session: Session,
    exposure_id: str,
    officer_code: str,
    settings: Settings,
    session_id: UUID | None = None,
) -> AssessResult:
    """Run one assess turn end to end and persist everything it produced."""

    exposure = queries.get_exposure(session, exposure_id)
    if exposure is None:
        raise GateError("no such exposure", exposure_id=exposure_id)

    officer = queries.officer_by_code(session, officer_code)
    if officer is None:
        raise EntitlementError("no such officer", officer_code=officer_code)

    turn_session_id = session_id or uuid4()
    queries.start_session(
        session,
        turn_session_id,
        correlation_id=str(turn_session_id),
        officer_id=officer.id,
        exposure_id=exposure_id,
    )
    session.commit()

    recorder = RunRecorder(
        session=session,
        exposure_id=exposure_id,
        officer_id=officer.id,
        session_id=turn_session_id,
        command="assess",
        turn_kind="assess",
    )
    recorder.start()

    subject = Subject(
        session_id=str(turn_session_id),
        officer_id=officer.id,
        officer_code=officer_code,
        exposure_id=exposure_id,
        worker_id=exposure.worker_id,
    )

    started = time.perf_counter()
    with open_checkpointer() as checkpointer:
        app = build_graph(settings.bounds, checkpointer=checkpointer)
        state = app.invoke(
            initial_state(subject),
            thread_config(
                officer.id,
                exposure_id,
                Participant.COORDINATOR,
                settings.bounds.max_recursion_depth,
            ),
        )
    duration = time.perf_counter() - started

    plan = state.get("dispatch_plan")
    if plan is not None:
        for worker in plan.validated_workers():
            recorder.dispatched(worker, plan.goals.get(worker, plan.rationale or "dispatched"))

    for verdict in state.get("reviewer_verdicts") or []:
        recorder.reviewer_verdict(
            verdict.iteration,
            verdict.worker,
            verdict.verdict,
            [{"reason": verdict.reason}] if verdict.reason else [],
        )

    # the graph decided which triggers fired; the harness records them and queues the dossier
    eligibility = record_eligibility(
        session=session,
        exposure_id=exposure_id,
        district=exposure.district,
        outcome=state.get("escalation") or EscalationOutcome(),
        recorder=recorder,
    )

    outcome = state.get("outcome") or "complete"
    dossier_id = queries.save_dossier(
        session,
        exposure_id,
        recorder.run_id,
        dossier_payload(state, exposure_id),
    )
    recorder.finish(outcome)
    queries.end_session(session, turn_session_id)
    session.commit()

    logger.info(
        "assess.completed",
        extra={
            "exposure_id": exposure_id,
            "run_id": str(recorder.run_id),
            "outcome": outcome,
            "duration_seconds": round(duration, 3),
        },
    )

    return AssessResult(
        exposure_id=exposure_id,
        run_id=recorder.run_id,
        outcome=outcome,
        dossier_id=dossier_id,
        duration_seconds=duration,
        eligibility=eligibility,
    )
