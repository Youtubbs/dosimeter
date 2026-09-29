"""Proposal tools used by Dosimeter workers.

Proposal tools validate typed worker proposals and return them without
performing persistence or external side effects.

The module also exposes Tool objects compatible with the shared
build_registry and ToolDispatcher infrastructure.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from dosimeter.graph.schemas import Subject
from dosimeter.tools.dispatcher import Tool
from dosimeter.workers.models import (
    NotificationProposal,
    WrittenReportProposal,
    EquipmentFinding,
)

PROPOSE_EQUIPMENT_FINDING = "propose_equipment_finding"
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


class ProposeEquipmentFindingInput(BaseModel):
    """Arguments supplied by the Equipment Worker."""

    model_config = ConfigDict(extra="forbid")

    finding: EquipmentFinding


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


def propose_equipment_finding(
    finding: EquipmentFinding | dict[str, Any],
) -> EquipmentFinding:
    """Validate and return an Equipment Worker finding.

    This function intentionally performs no database, S3, API, or other
    persistence operation.
    """

    if isinstance(finding, EquipmentFinding):
        return finding

    return EquipmentFinding.model_validate(finding)


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


def _handle_propose_equipment_finding(
    subject: Subject,
    arguments: ProposeEquipmentFindingInput,
) -> BaseModel:
    """Validate an equipment finding without performing side effects."""

    del subject

    return propose_equipment_finding(arguments.finding)


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

PROPOSE_EQUIPMENT_FINDING_TOOL = Tool(
    name=PROPOSE_EQUIPMENT_FINDING,
    description=(
        "Submit a typed equipment finding after evaluating the relevant "
        "equipment evidence. This tool validates the finding but does not "
        "send a report or write external state."
    ),
    input_model=ProposeEquipmentFindingInput,
    output_model=EquipmentFinding,
    handler=_handle_propose_equipment_finding,
)


def proposal_tools() -> list[Tool]:
    """Return the proposal tools for registration."""

    return [
        PROPOSE_NOTIFICATION_TOOL,
        PROPOSE_WRITTEN_REPORT_TOOL,
        PROPOSE_EQUIPMENT_FINDING_TOOL,
    ]
