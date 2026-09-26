""" The Pydantic models the graph passes between nodes """

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
