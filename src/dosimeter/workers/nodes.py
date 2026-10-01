"""Graph-node adapters for Dosimeter workers.

The graph owns routing and state merging. adapters connect the graph's
generic WorkerProposal contract to the typed Notification, Written Report
and Equipment workers.
"""

import logging
from collections.abc import Callable, Iterable

from pydantic import ValidationError

from dosimeter.graph.schemas import WorkerProposal
from dosimeter.graph.state import GraphState
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.tools.dispatcher import InvocationRecord, Tool
from dosimeter.workers.notification import run_notification_worker
from dosimeter.workers.written_report import run_written_report_worker
from dosimeter.guardrails.worker_output import (
    evaluate_worker_output,
    redact_worker_output,
)
from dosimeter.workers.equipment import run_equipment_worker


NodeFn = Callable[[GraphState], dict]

logger = logging.getLogger(__name__)

# the proposal kind each worker produces, and its goal when the plan names none
KINDS = {
    "notification": "notification",
    "written_report": "written_report",
    "equipment": "equipment_finding",
}
DEFAULT_GOALS = {
    "notification": "Evaluate whether regulatory notification is required.",
    "written_report": "Evaluate whether a regulatory written report is required.",
    "equipment": "Evaluate the reported radiographic equipment failure.",
}


def _runner(worker: str):
    # looked up per call, so a test can patch the module-level runner
    return {
        "notification": run_notification_worker,
        "written_report": run_written_report_worker,
        "equipment": run_equipment_worker,
    }[worker]


def _invocation_dicts(
    invocations: list[InvocationRecord],
) -> list[dict]:
    """Convert tool invocation records into graph-state data."""

    return [
        {
            "tool": invocation.tool,
            "arguments_sha256": invocation.arguments_sha256,
            "arguments": invocation.arguments,
            "result": invocation.result,
            "outcome": invocation.outcome,
            "duration_ms": invocation.duration_ms,
        }
        for invocation in invocations
    ]


def make_worker_node(
    worker: str,
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    recorder: RunRecorder | None = None,
) -> NodeFn:
    """Create one worker's graph node."""

    tools = list(shared_tools)

    def worker_node(state: GraphState) -> dict:
        subject = state["subject"].model_copy(update={"worker_id": worker})

        plan = state.get("dispatch_plan")
        goal = plan.goals.get(worker, DEFAULT_GOALS[worker]) if plan is not None else DEFAULT_GOALS[worker]

        try:
            proposal, invocations = _runner(worker)(
                subject=subject,
                ledger=ledger,
                shared_tools=tools,
                prompt=goal,
                recorder=recorder,
            )
        except (RuntimeError, ValidationError) as error:
            # no proposal means nothing is approved, so the turn escalates to a person instead of failing
            logger.warning("worker.no_proposal", extra={"worker": worker, "detail": str(error)})
            return {}

        guardrail_events = evaluate_worker_output(
            rule_results=getattr(proposal, "rule_results", ()),
            invocations=invocations,
            source=f"{worker}_worker",
            correlation_id=subject.session_id,
        )

        clean_payload, pii_events = redact_worker_output(
            proposal.model_dump(mode="json"),
            source=f"{worker}_worker",
            correlation_id=subject.session_id,
        )

        return {
            "proposals": {
                worker: WorkerProposal(
                    worker=worker,
                    kind=KINDS[worker],
                    payload=clean_payload,
                    citations=list(proposal.citations),
                ),
            },
            "rule_invocations": _invocation_dicts(invocations),
            # what the worker searched, so the Reviewer can re-read the chunks it cites
            "retrieval_log": [
                invocation.result
                for invocation in invocations
                if invocation.tool == "search_knowledge_base" and invocation.outcome == "ok" and invocation.result
            ],
            "guardrail_events": [
                *guardrail_events,
                *pii_events,
            ],
        }

    return worker_node


def make_notification_node(**kwargs) -> NodeFn:
    """Create the Notification Worker graph node."""

    return make_worker_node("notification", **kwargs)


def make_written_report_node(**kwargs) -> NodeFn:
    """Create the Written Report Worker graph node."""

    return make_worker_node("written_report", **kwargs)


def make_equipment_node(**kwargs) -> NodeFn:
    """Create the LangGraph Equipment Worker node."""

    return make_worker_node("equipment", **kwargs)
