"""Graph-node adapters for Dosimeter workers.

The graph owns routing and state merging. adapters connect the graph's
generic WorkerProposal contract to the typed Notification and Written Report
workers.
"""

from collections.abc import Callable, Iterable

from dosimeter.graph.schemas import Subject, WorkerProposal
from dosimeter.graph.state import GraphState
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.dispatcher import InvocationRecord, Tool
from dosimeter.workers.notification import run_notification_worker
from dosimeter.workers.written_report import run_written_report_worker
from dosimeter.guardrails.worker_output import (
    evaluate_worker_output,
    redact_worker_output,
)
from dosimeter.workers.equipment import run_equipment_worker


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

        guardrail_events = evaluate_worker_output(
            rule_results=proposal.rule_results,
            invocations=invocations,
            source="notification_worker",
            correlation_id=subject.session_id,
        )

        clean_payload, pii_events = redact_worker_output(
            proposal.model_dump(mode="json"),
            source="notification_worker",
            correlation_id=subject.session_id,
        )

        graph_proposal = WorkerProposal(
            worker="notification",
            kind="notification",
            payload=clean_payload,
            citations=list(proposal.citations),
        )

        return {
            "proposals": {
                "notification": graph_proposal,
            },
            "rule_invocations": _invocation_dicts(invocations),
            "guardrail_events": [
                *guardrail_events,
                *pii_events,
            ],
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

        guardrail_events = evaluate_worker_output(
            rule_results=proposal.rule_results,
            invocations=invocations,
            source="written_report_worker",
            correlation_id=subject.session_id,
        )

        clean_payload, pii_events = redact_worker_output(
            proposal.model_dump(mode="json"),
            source="written_report_worker",
            correlation_id=subject.session_id,
        )

        graph_proposal = WorkerProposal(
            worker="written_report",
            kind="written_report",
            payload=clean_payload,
            citations=list(proposal.citations),
        )

        return {
            "proposals": {
                "written_report": graph_proposal,
            },
            "rule_invocations": _invocation_dicts(invocations),
            "guardrail_events": [
                *guardrail_events,
                *pii_events,
            ],
        }

    return written_report_node


def make_equipment_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
):
    """Create the LangGraph Equipment Worker node."""

    def equipment_node(state: GraphState) -> dict:
        subject = _worker_subject(
            state["subject"],
            "equipment",
        )

        plan = state.get("dispatch_plan")

        goal = ""
        if plan is not None:
            goal = plan.goals.get(
                "equipment",
                "Evaluate the reported radiographic equipment failure.",
            )

        proposal, invocations = run_equipment_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=shared_tools,
            prompt=goal,
        )

        return {
            "proposals": {
                "equipment": WorkerProposal(
                    worker="equipment",
                    kind="equipment_finding",
                    payload=proposal.model_dump(mode="json"),
                    citations=list(proposal.citations),
                )
            },
            "rule_invocations": _invocation_dicts(invocations),
        }

    return equipment_node
