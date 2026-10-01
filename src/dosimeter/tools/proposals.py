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
from dosimeter.workers.models import NotificationProposal, WrittenReportProposal, EquipmentProposal

PROPOSE_NOTIFICATION = "propose_notification"
PROPOSE_WRITTEN_REPORT = "propose_written_report"
PROPOSE_EQUIPMENT_FINDING = "propose_equipment_finding"


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
    """Arguments supplied by the Equipment Report Worker."""

    model_config = ConfigDict(extra="forbid")

    proposal: EquipmentProposal


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
    proposal: EquipmentProposal | dict[str, Any],
) -> EquipmentProposal:
    """Validate and return an Equipment Worker proposal."""

    if isinstance(proposal, EquipmentProposal):
        return proposal

    return EquipmentProposal.model_validate(proposal)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _cited(proposal: BaseModel) -> BaseModel:
    # refused here, inside the worker's loop, the model can add the citation instead of failing review
    if not proposal.citations:
        raise ValueError("cite at least one chunk_id that search_knowledge_base returned")
    return proposal


def _handle_propose_notification(
    subject: Subject,
    arguments: ProposeNotificationInput,
) -> BaseModel:
    """Validate a notification proposal without performing side effects."""

    # The dispatcher injects the subject. Proposal tools intentionally
    # perform no subject-specific writes.
    del subject

    return _cited(propose_notification(arguments.proposal))


def _handle_propose_written_report(
    subject: Subject,
    arguments: ProposeWrittenReportInput,
) -> BaseModel:
    """Validate a written-report proposal without performing side effects."""

    del subject

    return _cited(propose_written_report(arguments.proposal))


def _handle_propose_equipment_finding(
    subject: Subject,
    arguments: ProposeEquipmentFindingInput,
) -> BaseModel:
    """Validate an equipment proposal without performing side effects."""

    # The dispatcher injects the subject. The proposal tool performs
    # no subject-specific writes.
    del subject

    return _cited(propose_equipment_finding(arguments.proposal))


# ---------------------------------------------------------------------------
# Shared Tool objects
# ---------------------------------------------------------------------------


PROPOSE_NOTIFICATION_TOOL = Tool(
    name=PROPOSE_NOTIFICATION,
    description=(
        "Submit a typed notification recommendation after evaluating the "
        "relevant deterministic rules. This tool validates the proposal "
        "but does not send a notification or write external state. "
        "citations must list the chunk_id of each source the finding rests on."
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
        "but does not send a report or write external state. "
        "citations must list the chunk_id of each source the finding rests on."
    ),
    input_model=ProposeWrittenReportInput,
    output_model=WrittenReportProposal,
    handler=_handle_propose_written_report,
)

PROPOSE_EQUIPMENT_FINDING_TOOL = Tool(
    name=PROPOSE_EQUIPMENT_FINDING,
    description=(
        "Submit a typed equipment finding after evaluating the "
        "reported radiographic equipment failure. This tool validates "
        "the proposal but does not submit or transmit a report. "
        "citations must list the chunk_id of each source the finding rests on."
    ),
    input_model=ProposeEquipmentFindingInput,
    output_model=EquipmentProposal,
    handler=_handle_propose_equipment_finding,
)


def proposal_tools() -> list[Tool]:
    """Return the proposal tools for registration."""

    return [PROPOSE_NOTIFICATION_TOOL, PROPOSE_WRITTEN_REPORT_TOOL, PROPOSE_EQUIPMENT_FINDING_TOOL]
