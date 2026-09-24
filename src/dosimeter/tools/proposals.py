"""Proposal tools used by Dosimeter workers.

These tools validate typed worker proposals and return them without
performing persistence or external side effects.
"""

from typing import Any


from dosimeter.workers.models import (
    NotificationProposal,
    WrittenReportProposal,
)


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


__all__ = [
    "NotificationProposal",
    "WrittenReportProposal",
    "propose_notification",
    "propose_written_report",
]
