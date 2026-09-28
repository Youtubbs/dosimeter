"""Graph-node adapters for Dosimeter workers.

The graph owns routing and state merging. adapters connect the graph's
generic WorkerProposal contract to the typed Notification and Written Report
workers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from dosimeter.graph.state import GraphState, Subject, WorkerProposal
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.base import InvocationRecord, Tool
from dosimeter.workers.notification import run_notification_worker
from dosimeter.workers.written_report import run_written_report_worker


NodeFn = Callable[[GraphState], dict]


def _worker_subject(
    subject: Subject,
    worker_id: str,
) -> Subject:
    """Return the current subject scoped to one worker."""

    return subject.model_copy(
        update={"worker_id": worker_id},
    )


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


def make_notification_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
) -> NodeFn:
    """Create the Notification Worker graph node."""

    tools = list(shared_tools)

    def notification_node(state: GraphState) -> dict:
        subject = _worker_subject(
            state["subject"],
            "notification",
        )

        plan = state.get("dispatch_plan")
        prompt = (
            plan.goals.get(
                "notification",
                "Evaluate whether regulatory notification is required.",
            )
            if plan is not None
            else "Evaluate whether regulatory notification is required."
        )

        proposal, invocations = run_notification_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=tools,
            prompt=prompt,
        )

        graph_proposal = WorkerProposal(
            worker="notification",
            kind="notification",
            payload=proposal.model_dump(mode="json"),
            citations=list(proposal.citations),
        )

        return {
            "proposals": {
                "notification": graph_proposal,
            },
            "rule_invocations": _invocation_dicts(invocations),
        }

    return notification_node


def make_written_report_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
) -> NodeFn:
    """Create the Written Report Worker graph node."""

    tools = list(shared_tools)

    def written_report_node(state: GraphState) -> dict:
        subject = _worker_subject(
            state["subject"],
            "written_report",
        )

        plan = state.get("dispatch_plan")
        prompt = (
            plan.goals.get(
                "written_report",
                "Evaluate whether a regulatory written report is required.",
            )
            if plan is not None
            else "Evaluate whether a regulatory written report is required."
        )

        proposal, invocations = run_written_report_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=tools,
            prompt=prompt,
        )

        graph_proposal = WorkerProposal(
            worker="written_report",
            kind="written_report",
            payload=proposal.model_dump(mode="json"),
            citations=list(proposal.citations),
        )

        return {
            "proposals": {
                "written_report": graph_proposal,
            },
            "rule_invocations": _invocation_dicts(invocations),
        }

    return written_report_node


__all__ = [
    "make_notification_node",
    "make_written_report_node",
]
