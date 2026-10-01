"""
One assess turn: build the graph, run it on its own thread, record what it did,
record the eligibility check, and store the dossier.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from dosimeter.config.settings import Settings
from dosimeter.errors import BudgetError, EntitlementError, GateError
from dosimeter.graph.checkpointer import open_checkpointer
from dosimeter.graph.graph import build_graph
from dosimeter.graph.schemas import Subject
from dosimeter.graph.state import initial_state
from dosimeter.graph.threads import Participant, thread_config
from dosimeter.harness.budgets import RECURSION_DEPTH, BudgetBreach, SessionLedger
from dosimeter.harness.eligibility import EligibilityResult, record_eligibility
from dosimeter.harness.escalation import EscalationOutcome
from dosimeter.harness.run_record import RunRecorder
from dosimeter.repository import Session, queries
from dosimeter.repository.models import Exposure
from dosimeter.tools.registry import shared_tools

logger = logging.getLogger(__name__)


class AssessResult(BaseModel):
    exposure_id: str
    run_id: UUID
    outcome: str
    dossier_id: int
    duration_seconds: float
    eligibility: EligibilityResult
    # set when a bound stopped the turn early, naming the ceiling
    partial: dict[str, Any] | None = None

    @property
    def escalated(self) -> bool:
        return self.eligibility.escalated


def dossier_payload(state: dict, exposure_id: str) -> dict:
    """What is stored for the renderer to read back cold."""

    proposals = state.get("proposals") or {}
    escalation = state.get("escalation")
    guardrail_events = state.get("guardrail_events") or []

    return {
        "exposure_id": exposure_id,
        "outcome": state.get("outcome"),
        "workers": sorted(proposals),
        "proposals": {name: item.model_dump(mode="json") for name, item in proposals.items()},
        "rule_invocations": state.get("rule_invocations") or [],
        "sources": state.get("retrieval_log") or [],
        "guardrail_events": [event.model_dump(mode="json") for event in guardrail_events],
        "escalation_signals": (escalation.names() if escalation else []),
        "reviewer_verdicts": [
            item.model_dump(mode="json") for item in state.get("reviewer_verdicts") or []
        ],
    }


def packet_facts(session: Session, exposure_id: str) -> list[str]:
    """Each extracted field that has a value, once, as "key: value"."""

    facts = []
    for row in queries.list_extracted_fields(session, exposure_id):
        fact = f"{row.field_key.rstrip(':').strip()}: {row.value.strip()}" if row.value else ""
        if row.value and row.value.strip() and fact not in facts:
            facts.append(fact)
    return facts


# a field whose name says it holds a dose; the rest of the form (headers, signatures) never stops a turn
DOSE_FIELD_WORDS = ("dose equivalent", "tede", "intake")


# the three dose quantities every rule reads, and the words their extracted field names use
REQUIRED_DOSES = {
    "Total Effective Dose Equivalent": ("tede", "total effective dose"),
    "Lens Dose Equivalent": ("lens dose",),
    "Shallow Dose Equivalent": ("shallow dose equivalent",),
}


def missing_dose_fields(session: Session, exposure_id: str) -> list[str]:
    """Required dose quantities the packet gave no number for ("Not specified", or no field at all)."""

    read = [
        (row.field_key.lower().replace("-", " "), row.value or "")
        for row in queries.list_extracted_fields(session, exposure_id)
        if "year to date" not in row.field_key.lower().replace("-", " ")
    ]
    return [
        name
        for name, words in REQUIRED_DOSES.items()
        if not any(any(word in key for word in words) and re.search(r"\d", value) for key, value in read)
    ]


def low_confidence_dose_fields(session: Session, exposure_id: str, floor: float) -> list[str]:
    """Dose fields Textract read with less confidence than the floor, once each."""

    fields = []
    for row in queries.list_extracted_fields(session, exposure_id):
        key = row.field_key.rstrip(":").strip()
        is_dose = any(word in key.lower().replace("-", " ") for word in DOSE_FIELD_WORDS)
        if is_dose and row.confidence is not None and row.confidence < floor and key not in fields:
            fields.append(key)
    return fields


@dataclass
class Turn:
    """What one graph turn left behind, before the command decides what to store."""

    state: dict[str, Any]
    exposure: Exposure
    session_id: UUID
    recorder: RunRecorder
    ledger: SessionLedger
    partial: dict[str, Any] | None
    duration: float


def run_turn(
    session: Session,
    exposure_id: str,
    officer_code: str,
    settings: Settings,
    command: str = "assess",
    session_id: UUID | None = None,
    question: str | None = None,
    previous_dossier: str | None = None,
    runtime_arn: str | None = None,
    runtime_session_id: str | None = None,
    access_token: str | None = None,
) -> Turn:
    """One turn through the graph with the turn's budget and run record. assess and ask share it."""

    exposure = queries.get_exposure(session, exposure_id)
    if exposure is None:
        raise GateError("no such exposure", exposure_id=exposure_id)

    officer = queries.officer_by_code(session, officer_code)
    if officer is None:
        raise EntitlementError("no such officer", officer_code=officer_code)

    # each assess opens a session; a follow-up turn passes session_id to continue it, ceiling and all
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
        command=command,
        turn_kind=command,
        runtime_arn=runtime_arn,
        runtime_session_id=runtime_session_id,
    )
    recorder.start()

    input_tokens, output_tokens = queries.session_token_usage(session, turn_session_id)
    ledger = SessionLedger(
        settings.bounds,
        session_input_tokens=input_tokens,
        session_output_tokens=output_tokens,
    )

    subject = Subject(
        session_id=str(turn_session_id),
        officer_id=officer.id,
        officer_code=officer_code,
        exposure_id=exposure_id,
        worker_id=exposure.worker_id,
    )

    # Local execution reaches API-backed read tools over HTTP.
    # In deployment, these capabilities are exposed through AgentCore Gateway.
    transport = HttpTransport(
        base_url=settings.tool_api_url,
        officer_code=subject.officer_code,
    )
    tool_registry = build_tool_registry(transport)
    shared_tools = list(tool_registry.values())

    config = thread_config(
        officer.id,
        exposure_id,
        Participant.COORDINATOR,
        settings.bounds.max_recursion_depth,
    )

    breach: BudgetBreach | None = None
    started = time.perf_counter()
    with open_checkpointer() as checkpointer:
        # each turn starts fresh; what earlier turns concluded lives in the dossier and run records
        checkpointer.delete_thread(config["configurable"]["thread_id"])

        app = build_graph(
            settings.bounds,
            ledger=ledger,
            recorder=recorder,
            # the read tools reach the tool API as this officer, directly or through the Gateway
            shared_tools=shared_tools(settings, officer_code, access_token),
            checkpointer=checkpointer,
        )

        try:
            state = app.invoke(
                initial_state(
                    subject,
                    packet_facts(session, exposure_id),
                    low_confidence_dose_fields(session, exposure_id, settings.confidence_floor),
                    missing_dose_fields(session, exposure_id),
                    question=question,
                    previous_dossier=previous_dossier,
                ),
                config,
            )
        except BudgetError as error:
            breach = BudgetBreach(
                ceiling=error.context["ceiling"],
                limit=error.context["limit"],
                used=error.context["used"],
            )
        except GraphRecursionError:
            breach = BudgetBreach(
                ceiling=RECURSION_DEPTH,
                limit=settings.bounds.max_recursion_depth,
                used=settings.bounds.max_recursion_depth,
            )

        # a breach stops the turn; the steps that finished are the partial response
        if breach is not None:
            state = app.get_state(config).values
    duration = time.perf_counter() - started

    partial = None
    if breach is not None:
        finished = ", ".join(sorted(state.get("proposals") or {})) or "none"
        partial = ledger.partial_response(breach, partial=f"workers finished: {finished}")
        recorder.guardrail_event(
            stage="bounds",
            action="terminated",
            guardrail_id=breach.ceiling,
            detail=partial,
        )
        logger.warning(
            f"{command}.stopped",
            extra={"exposure_id": exposure_id, "ceiling": breach.ceiling},
        )

    for verdict in state.get("reviewer_verdicts") or []:
        recorder.reviewer_verdict(
            verdict.iteration,
            verdict.worker,
            verdict.verdict,
            [{"reason": verdict.reason}] if verdict.reason else [],
        )

    for event in state.get("guardrail_events") or []:
        recorder.guardrail_event(
            stage="output",
            action=event.remedy.value,
            guardrail_id=event.trigger,
            detail={
                "correlation_id": event.correlation_id,
                "trigger": event.trigger,
                "source": event.source,
                "detail": event.detail,
            },
        )

    return Turn(
        state=state,
        exposure=exposure,
        session_id=turn_session_id,
        recorder=recorder,
        ledger=ledger,
        partial=partial,
        duration=duration,
    )


def run_assess(
    session: Session,
    exposure_id: str,
    officer_code: str,
    settings: Settings,
    session_id: UUID | None = None,
    runtime_arn: str | None = None,
    runtime_session_id: str | None = None,
    access_token: str | None = None,
) -> AssessResult:
    """Run one assess turn end to end and persist everything it produced."""

    turn = run_turn(
        session,
        exposure_id,
        officer_code,
        settings,
        command="assess",
        session_id=session_id,
        runtime_arn=runtime_arn,
        runtime_session_id=runtime_session_id,
        access_token=access_token,
    )
    state, recorder = turn.state, turn.recorder

    # the graph decided which triggers fired; the harness records them and queues the dossier
    eligibility = record_eligibility(
        session=session,
        exposure_id=exposure_id,
        district=turn.exposure.district,
        outcome=state.get("escalation") or EscalationOutcome(),
        recorder=recorder,
    )

    outcome = "partial" if turn.partial is not None else state.get("outcome") or "complete"

    payload = dossier_payload(state, exposure_id)
    if turn.partial is not None:
        payload["partial"] = turn.partial

    dossier_id = queries.save_dossier(
        session,
        exposure_id,
        recorder.run_id,
        payload,
    )
    recorder.finish(outcome)
    queries.end_session(session, turn.session_id)
    session.commit()

    logger.info(
        "assess.completed",
        extra={
            "exposure_id": exposure_id,
            "run_id": str(recorder.run_id),
            "outcome": outcome,
            "duration_seconds": round(turn.duration, 3),
        },
    )

    return AssessResult(
        exposure_id=exposure_id,
        run_id=recorder.run_id,
        outcome=outcome,
        dossier_id=dossier_id,
        duration_seconds=turn.duration,
        eligibility=eligibility,
        partial=turn.partial,
    )
