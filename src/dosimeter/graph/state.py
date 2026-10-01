"""State that will be used by every node in our graph."""

import operator
from typing import Annotated, Any, TypedDict

from dosimeter.graph.schemas import (
    DispatchPlan,
    ReviewerVerdict,
    Subject,
    WorkerProposal,
)
from dosimeter.harness.escalation import EscalationOutcome
from dosimeter.guardrails.events import GuardrailEvent


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
    # what the packet says, so the Coordinator can tell which workers apply
    packet_facts: list[str]
    # dose fields extracted below the confidence floor, or not readable at all; any of them stops the turn
    low_confidence_fields: list[str]
    missing_dose_fields: list[str]
    # set on an ask turn: the officer's question and what the earlier turn concluded
    question: str | None
    previous_dossier: str | None
    dispatch_plan: DispatchPlan | None
    proposals: Annotated[dict[str, WorkerProposal], merge_proposals]
    reviewer_verdicts: Annotated[list[ReviewerVerdict], operator.add]
    reviewer_iterations: int
    rule_invocations: Annotated[list[dict[str, Any]], operator.add]
    retrieval_log: Annotated[list[dict[str, Any]], operator.add]
    guardrail_events: Annotated[list[GuardrailEvent], operator.add]
    usage: Annotated[dict[str, int], add_usage]
    escalation: EscalationOutcome | None
    outcome: str | None


def initial_state(
    subject: Subject,
    packet_facts: list[str] | None = None,
    low_confidence_fields: list[str] | None = None,
    missing_dose_fields: list[str] | None = None,
    question: str | None = None,
    previous_dossier: str | None = None,
) -> GraphState:
    return GraphState(
        subject=subject,
        packet_facts=packet_facts or [],
        low_confidence_fields=low_confidence_fields or [],
        missing_dose_fields=missing_dose_fields or [],
        question=question,
        previous_dossier=previous_dossier,
        dispatch_plan=None,
        proposals={},
        reviewer_verdicts=[],
        reviewer_iterations=0,
        rule_invocations=[],
        retrieval_log=[],
        guardrail_events=[],
        usage={},
        escalation=None,
        outcome=None,
    )
