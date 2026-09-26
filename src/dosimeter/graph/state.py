""" State that will be used by every node in our graph """

import operator
from typing import Annotated, Any, TypedDict

from dosimeter.graph.schemas import DispatchPlan, ReviewerVerdict, Subject, WorkerProposal
from dosimeter.harness.escalation import EscalationOutcome


def merge_proposals(
    left: dict[str, WorkerProposal],
    right: dict[str, WorkerProposal],
) -> dict[str, WorkerProposal]:
    """Parallel legs write different keys, so a merge keeps both."""

    merged = dict(left)
    merged.update(right)
    return merged


def add_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, 0) + value
    return merged


class GraphState(TypedDict, total=False):
    """Everything a turn carries between nodes."""

    subject: Subject
    dispatch_plan: DispatchPlan | None
    proposals: Annotated[dict[str, WorkerProposal], merge_proposals]
    reviewer_verdicts: Annotated[list[ReviewerVerdict], operator.add]
    reviewer_iterations: int
    rule_invocations: Annotated[list[dict[str, Any]], operator.add]
    retrieval_log: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[dict[str, int], add_usage]
    escalation: EscalationOutcome | None
    outcome: str | None


def initial_state(subject: Subject) -> GraphState:
    return GraphState(
        subject=subject,
        dispatch_plan=None,
        proposals={},
        reviewer_verdicts=[],
        reviewer_iterations=0,
        rule_invocations=[],
        retrieval_log=[],
        usage={},
        escalation=None,
        outcome=None,
    )
