"""Proposal tools used by Dosimeter workers.

Proposal tools validate typed worker proposals and return them without
performing persistence or external side effects.

The module also exposes Tool objects compatible with the shared
ToolRegistry and ToolDispatcher infrastructure.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from dosimeter.graph.state import Subject
from dosimeter.tools.base import Tool
from dosimeter.workers.models import (
    NotificationProposal,
    WrittenReportProposal,
)

PROPOSE_NOTIFICATION = "propose_notification"
PROPOSE_WRITTEN_REPORT = "propose_written_report"


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------


class ProposeNotificationInput(BaseModel):
    """Arguments supplied by the Notification Worker."""

    model_config = ConfigDict(extra="forbid")

    proposal: NotificationProposal


class ProposeWrittenReportInput(BaseModel):
    """Arguments supplied by the Written Report Worker."""

    model_config = ConfigDict(extra="forbid")

    proposal: WrittenReportProposal


# ---------------------------------------------------------------------------
# Existing direct proposal helpers
# ---------------------------------------------------------------------------


def propose_notification(
    proposal: NotificationProposal | dict[str, Any],
) -> NotificationProposal:
    """Validate and return a Notification Worker proposal.

    This function intentionally performs no database, S3, API, or other
    persistence operation.
    """

    if isinstance(proposal, NotificationProposal):
        return proposal

    return NotificationProposal.model_validate(proposal)


def propose_written_report(
    proposal: WrittenReportProposal | dict[str, Any],
) -> WrittenReportProposal:
    """Validate and return a Written Report Worker proposal.

    This function intentionally performs no database, S3, API, or other
    persistence operation.
    """

    if isinstance(proposal, WrittenReportProposal):
        return proposal

    return WrittenReportProposal.model_validate(proposal)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handle_propose_notification(
    subject: Subject,
    arguments: ProposeNotificationInput,
) -> BaseModel:
    """Validate a notification proposal without performing side effects."""

    # The dispatcher injects the subject. Proposal tools intentionally
    # perform no subject-specific writes.
    del subject

    return propose_notification(arguments.proposal)


def _handle_propose_written_report(
    subject: Subject,
    arguments: ProposeWrittenReportInput,
) -> BaseModel:
    """Validate a written-report proposal without performing side effects."""

    del subject

    return propose_written_report(arguments.proposal)


# ---------------------------------------------------------------------------
# Shared Tool objects
# ---------------------------------------------------------------------------


PROPOSE_NOTIFICATION_TOOL = Tool(
    name=PROPOSE_NOTIFICATION,
    description=(
        "Submit a typed notification recommendation after evaluating the "
        "relevant deterministic rules. This tool validates the proposal "
        "but does not send a notification or write external state."
    ),
    input_model=ProposeNotificationInput,
    output_model=NotificationProposal,
    handler=_handle_propose_notification,
)


PROPOSE_WRITTEN_REPORT_TOOL = Tool(
    name=PROPOSE_WRITTEN_REPORT,
    description=(
        "Submit a typed written-report recommendation after evaluating the "
        "relevant deterministic rules. This tool validates the proposal "
        "but does not send a report or write external state."
    ),
    input_model=ProposeWrittenReportInput,
    output_model=WrittenReportProposal,
    handler=_handle_propose_written_report,
)


def proposal_tools() -> list[Tool]:
    """Return the proposal tools for registration."""

    return [
        PROPOSE_NOTIFICATION_TOOL,
        PROPOSE_WRITTEN_REPORT_TOOL,
    ]


__all__ = [
    "PROPOSE_NOTIFICATION",
    "PROPOSE_NOTIFICATION_TOOL",
    "PROPOSE_WRITTEN_REPORT",
    "PROPOSE_WRITTEN_REPORT_TOOL",
    "NotificationProposal",
    "ProposeNotificationInput",
    "ProposeWrittenReportInput",
    "WrittenReportProposal",
    "proposal_tools",
    "propose_notification",
    "propose_written_report",
]
