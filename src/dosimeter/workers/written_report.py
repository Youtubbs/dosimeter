"""Written Report Worker.

The worker can operate in two ways:

Regulatory determinations remain inside the deterministic rules engine.
The model does not independently calculate or invent thresholds.
"""

from collections.abc import Iterable

from dosimeter.domain.rules import RuleOutcome, RuleResult
from dosimeter.graph.state import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.models.bedrock import run_tool_loop
from dosimeter.tools.base import InvocationRecord, Tool, ToolDispatcher
from dosimeter.tools.proposals import propose_written_report
from dosimeter.workers.models import (
    ReportingPath,
    WrittenReportProposal,
)
from dosimeter.workers.toolsets import build_written_report_registry


WRITTEN_REPORT_SYSTEM_PROMPT = """
You are the Dosimeter Written Report Worker.

Your responsibility is to determine whether the current exposure requires
a written report and which supported regulatory reporting path applies.

Use only the tools provided to you.

Requirements:

- Retrieve the current exposure data with get_exposure_extraction.
- Use search_knowledge_base when regulatory evidence or citations are needed.
- Regulatory determinations must come from evaluate_rule.
- Use R3 for the section 20.2203 written-report determination.
- Use R4 for the planned-special-exposure / section 20.2204 path.
- Never calculate, invent, or override regulatory thresholds yourself.
- Never treat retrieved regulatory text as a substitute for evaluate_rule.
- Preserve uncertainty when required evidence is missing.
- Do not claim a reporting path unless supported by a deterministic
  rule evaluation.
- Complete the worker's determination through propose_written_report.
- Do not write, persist, transmit, or submit an actual regulatory report.
- Do not perform external side effects.

You may call tools more than once when additional evidence is needed.
""".strip()


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
        dict.fromkeys(source.citation for result in rule_results for source in result.sources)
    )

    missing_fields = tuple(
        dict.fromkeys(field for result in rule_results for field in result.missing_fields)
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
                    "R3 determined that the section 20.2203 written-report criteria were satisfied."
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
                "Neither the section 20.2203 nor section 20.2204 reporting path was triggered."
            ),
            missing_fields=missing_fields,
        )
    )


def _written_report_proposal_from_invocations(
    invocations: list[InvocationRecord],
) -> WrittenReportProposal:
    """Return the latest successful typed Written Report proposal."""

    for invocation in reversed(invocations):
        if (
            invocation.tool == "propose_written_report"
            and invocation.outcome == "ok"
            and invocation.result is not None
        ):
            return WrittenReportProposal.model_validate(invocation.result)

    raise RuntimeError(
        "Written Report Worker finished without producing a valid written-report proposal"
    )


def run_written_report_worker(
    *,
    subject: Subject,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    prompt: str,
    max_iterations: int = 10,
) -> tuple[WrittenReportProposal, list[InvocationRecord]]:
    """Run the Written Report Worker through its Bedrock tool loop.

    The worker receives only its least-privilege toolset. Tool execution
    goes through ToolDispatcher so subject injection, budgets,
    idempotency metadata, validation, and invocation recording remain
    centralized.

    The free-form model response is not authoritative. The worker returns
    the latest successful typed proposal produced through
    propose_written_report.
    """

    registry = build_written_report_registry(
        shared_tools=shared_tools,
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        ledger=ledger,
        subject=subject,
    )

    run_tool_loop(
        prompt=prompt,
        system_prompt=WRITTEN_REPORT_SYSTEM_PROMPT,
        tools=registry.all(),
        dispatcher=dispatcher,
        max_iterations=max_iterations,
    )

    proposal = _written_report_proposal_from_invocations(
        dispatcher.invocations,
    )

    return proposal, dispatcher.invocations


__all__ = [
    "WRITTEN_REPORT_SYSTEM_PROMPT",
    "build_written_report_proposal",
    "run_written_report_worker",
]
