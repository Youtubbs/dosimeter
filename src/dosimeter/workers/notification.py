"""Notification Worker.

Builds a typed notification proposal from deterministic R1 and R2
rule results. The worker does not independently calculate regulatory
thresholds and performs no persistence.
"""

from dosimeter.domain.rules import RuleOutcome, RuleResult
from dosimeter.tools.proposals import propose_notification
from dosimeter.workers.models import (
    NotificationClock,
    NotificationProposal,
)


def build_notification_proposal(
    *,
    r1_result: RuleResult,
    r2_result: RuleResult,
) -> NotificationProposal:
    """Build a notification proposal from recorded R1 and R2 results.

    Priority:
        1. R1 REQUIRED -> immediate notification
        2. R2 REQUIRED -> 24-hour notification
        3. Missing/insufficient rule data -> no definitive notification
        4. Otherwise -> no notification required

    Regulatory threshold calculations remain inside R1 and R2.
    """

    rule_results = (r1_result, r2_result)

    citations = tuple(
        dict.fromkeys(source.citation for result in rule_results for source in result.sources)
    )

    missing_fields = tuple(
        dict.fromkeys(field for result in rule_results for field in result.missing_fields)
    )

    # R1 has the highest notification priority.
    if r1_result.outcome == RuleOutcome.REQUIRED:
        return propose_notification(
            NotificationProposal(
                notification_required=True,
                clock=NotificationClock.IMMEDIATE,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "R1 determined that the immediate-notification criteria were satisfied."
                ),
                missing_fields=missing_fields,
            )
        )

    # If immediate notification did not fire, evaluate the R2 result.
    if r2_result.outcome == RuleOutcome.REQUIRED:
        return propose_notification(
            NotificationProposal(
                notification_required=True,
                clock=NotificationClock.TWENTY_FOUR_HOUR,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "R2 determined that the 24-hour notification criteria were satisfied."
                ),
                missing_fields=missing_fields,
            )
        )

    # Do not make a definitive regulatory conclusion when one of the
    # deterministic rules reports insufficient data.
    if (
        r1_result.outcome == RuleOutcome.INSUFFICIENT_DATA
        or r2_result.outcome == RuleOutcome.INSUFFICIENT_DATA
    ):
        return propose_notification(
            NotificationProposal(
                notification_required=False,
                clock=NotificationClock.NONE,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "A definitive notification determination could not "
                    "be completed because required rule inputs are missing."
                ),
                missing_fields=missing_fields,
            )
        )

    return propose_notification(
        NotificationProposal(
            notification_required=False,
            clock=NotificationClock.NONE,
            rule_results=rule_results,
            citations=citations,
            explanation=("Neither R1 nor R2 determined that a notification tier was required."),
            missing_fields=missing_fields,
        )
    )
