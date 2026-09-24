"""
Thread ids for the graph.

One thread per participant per exposure per officer, derived the same way by
every command, so an escalated dossier is a row that any later command can pick
up rather than a process that has to stay alive.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

THREAD_ID_FORMAT = "dosimeter:v1:{officer_id}:{exposure_id}:{participant}"


class Participant(StrEnum):
    """Everything that keeps its own checkpointed conversation."""

    COORDINATOR = "coordinator"
    NOTIFICATION = "notification"
    WRITTEN_REPORT = "written_report"
    EQUIPMENT = "equipment"
    REVIEWER = "reviewer"


WORKERS = (Participant.NOTIFICATION, Participant.WRITTEN_REPORT, Participant.EQUIPMENT)


def thread_id(officer_id: int, exposure_id: str, participant: Participant | str) -> str:
    """The one string every command derives for this participant."""

    name = participant.value if isinstance(participant, Participant) else str(participant)
    if name not in {item.value for item in Participant}:
        raise ValueError(f"unknown participant: {name}")

    return THREAD_ID_FORMAT.format(
        officer_id=officer_id,
        exposure_id=exposure_id,
        participant=name,
    )


def thread_ids(officer_id: int, exposure_id: str) -> dict[str, str]:
    """Every thread for one officer and one exposure, keyed by participant."""

    return {item.value: thread_id(officer_id, exposure_id, item) for item in Participant}


def thread_config(
    officer_id: int,
    exposure_id: str,
    participant: Participant | str,
    recursion_limit: int,
) -> dict[str, Any]:
    """The config a graph run takes: which thread, and how deep it may go."""

    return {
        "configurable": {"thread_id": thread_id(officer_id, exposure_id, participant)},
        "recursion_limit": recursion_limit,
    }
