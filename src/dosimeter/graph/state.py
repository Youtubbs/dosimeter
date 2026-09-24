"""
The typed state the graph carries, and the reducers
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.graph.threads import Participant

WORKER_NAMES = ("notification", "written_report", "equipment")


class DispatchPlan(BaseModel):
    """What the Coordinator decided. The model chooses what, the graph routes it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workers: list[str] = Field(default_factory=list)
    goals: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""
    redispatch_trigger: str | None = None

    def validated_workers(self) -> list[str]:
        unknown = [name for name in self.workers if name not in WORKER_NAMES]
        if unknown:
            raise ValueError(f"unknown workers in dispatch plan: {', '.join(unknown)}")
        return list(self.workers)


class WorkerProposal(BaseModel):
    """One worker's output. Proposals are validated and never written by a tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    worker: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)


class ReviewerVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    iteration: int
    worker: str
    verdict: str
    reason: str = ""


class Subject(BaseModel):
    """Who and what this run is about. Never model-editable, never a tool argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    officer_id: int
    officer_code: str
    exposure_id: str
    worker_id: str | None = None


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
    escalation_signals: Annotated[list[str], operator.add]
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
        escalation_signals=[],
        outcome=None,
    )


def participant_for(worker: str) -> Participant:
    return Participant(worker)
