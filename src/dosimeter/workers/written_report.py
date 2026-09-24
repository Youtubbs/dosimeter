"""Written Report Worker.

Builds a typed written-report proposal from deterministic R3 and R4
rule results. The worker does not independently calculate regulatory
thresholds and performs no persistence.
"""

from dosimeter.domain.rules import RuleOutcome, RuleResult
from dosimeter.tools.proposals import propose_written_report
from dosimeter.workers.models import (
    ReportingPath,
    WrittenReportProposal,
)


def build_written_report_proposal(
    *,
    r3_result: RuleResult,
    r4_result: RuleResult,
) -> WrittenReportProposal:
    """Build a written-report proposal from recorded R3 and R4 results.

    The normal written-report path is section 20.2203.

    When R4 establishes a valid planned special exposure, the alternate
    section 20.2204 reporting path applies.

    Regulatory determinations remain inside R3 and R4.
    """

    rule_results = (r3_result, r4_result)

    citations = tuple(
        dict.fromkeys(
            source.citation
            for result in rule_results
            for source in result.sources
        )
    )

    missing_fields = tuple(
        dict.fromkeys(
            field
            for result in rule_results
            for field in result.missing_fields
        )
    )

    # A valid planned special exposure follows the alternate
    # section 20.2204 reporting path.
    if r4_result.outcome == RuleOutcome.VALID:
        return propose_written_report(
            WrittenReportProposal(
                report_required=True,
                reporting_path=ReportingPath.SECTION_20_2204,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "R4 determined that the planned special exposure "
                    "conditions were satisfied, so the section 20.2204 "
                    "reporting path applies."
                ),
                missing_fields=missing_fields,
            )
        )

    # Otherwise use the normal R3 written-report determination.
    if r3_result.outcome == RuleOutcome.REQUIRED:
        return propose_written_report(
            WrittenReportProposal(
                report_required=True,
                reporting_path=ReportingPath.SECTION_20_2203,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "R3 determined that the section 20.2203 written-report "
                    "criteria were satisfied."
                ),
                missing_fields=missing_fields,
            )
        )

    # Never manufacture a definitive determination when either relevant
    # rule reports insufficient data.
    if (
        r3_result.outcome == RuleOutcome.INSUFFICIENT_DATA
        or r4_result.outcome == RuleOutcome.INSUFFICIENT_DATA
    ):
        return propose_written_report(
            WrittenReportProposal(
                report_required=False,
                reporting_path=ReportingPath.NONE,
                rule_results=rule_results,
                citations=citations,
                explanation=(
                    "A definitive written-report determination could not "
                    "be completed because required rule inputs are missing."
                ),
                missing_fields=missing_fields,
            )
        )

    return propose_written_report(
        WrittenReportProposal(
            report_required=False,
            reporting_path=ReportingPath.NONE,
            rule_results=rule_results,
            citations=citations,
            explanation=(
                "Neither the section 20.2203 nor section 20.2204 "
                "reporting path was triggered."
            ),
            missing_fields=missing_fields,
        )
    )
