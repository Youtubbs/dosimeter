"""Notification Worker.

The worker can operate in two ways:

1. Deterministically build a typed NotificationProposal from recorded
   R1 and R2 results.
2. Run as a Bedrock tool-calling worker that retrieves evidence,
   requests deterministic rule evaluations, and proposes a notification.

Regulatory thresholds remain inside the deterministic rules engine.
The model does not independently calculate or invent thresholds.
"""

from collections.abc import Iterable

from dosimeter.domain.rules import RuleOutcome, RuleResult
from dosimeter.graph.state import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.models.bedrock import run_tool_loop
from dosimeter.tools.base import Tool, ToolDispatcher, InvocationRecord
from dosimeter.tools.proposals import propose_notification
from dosimeter.workers.models import (
    NotificationClock,
    NotificationProposal,
)
from dosimeter.workers.toolsets import build_notification_registry


NOTIFICATION_SYSTEM_PROMPT = """
You are the Dosimeter Notification Worker.

Your responsibility is to determine whether the current exposure requires
an immediate notification, a 24-hour notification, or no definitive
notification determination.

Use only the tools provided to you.

Requirements:

- Retrieve the current exposure data with get_exposure_extraction.
- Use search_knowledge_base when regulatory evidence or citations are needed.
- Regulatory threshold determinations must come from evaluate_rule.
- Use R1 for immediate-notification evaluation.
- Use R2 for 24-hour-notification evaluation.
- Never calculate, invent, or override regulatory thresholds yourself.
- Never treat retrieved regulatory text as a substitute for evaluate_rule.
- If required information is missing, preserve that uncertainty.
- Do not claim a notification tier unless supported by a deterministic
  rule evaluation.
- Complete the worker's determination through propose_notification.
- Do not perform persistence, transmission, or external side effects.

You may call tools more than once when additional evidence is needed.
""".strip()


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


def _notification_proposal_from_invocations(
    invocations: list[InvocationRecord],
) -> NotificationProposal:
    """Return the typed proposal produced by the Notification Worker."""

    for invocation in reversed(invocations):
        if (
            invocation.tool == "propose_notification"
            and invocation.outcome == "ok"
            and invocation.result is not None
        ):
            return NotificationProposal.model_validate(invocation.result)

    raise RuntimeError(
        "Notification Worker finished without producing a valid notification proposal"
    )


def run_notification_worker(
    *,
    subject: Subject,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    prompt: str,
    max_iterations: int = 10,
) -> tuple[NotificationProposal, list[InvocationRecord]]:
    """Run the Notification Worker through its Bedrock tool loop.

    The worker receives only its least-privilege toolset. Tool execution
    goes through ToolDispatcher so subject injection, budgets,
    idempotency metadata, validation, and invocation recording remain
    centralized.
    """

    registry = build_notification_registry(
        shared_tools=shared_tools,
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        ledger=ledger,
        subject=subject,
    )

    run_tool_loop(
        prompt=prompt,
        system_prompt=NOTIFICATION_SYSTEM_PROMPT,
        tools=registry.all(),
        dispatcher=dispatcher,
        max_iterations=max_iterations,
    )

    proposal = _notification_proposal_from_invocations(
        dispatcher.invocations,
    )

    return proposal, dispatcher.invocations


__all__ = [
    "NOTIFICATION_SYSTEM_PROMPT",
    "build_notification_proposal",
    "run_notification_worker",
]
