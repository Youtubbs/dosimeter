"""Equipment Worker.

The Equipment Worker evaluates whether a reported radiographic equipment
failure requires regulatory reporting.

The worker uses regulatory evidence and deterministic/current regulatory
text. Similar exposures are only precedent candidates and never determine
the current finding.
"""

from collections.abc import Iterable

from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.models.bedrock import run_tool_loop
from dosimeter.prompts import EQUIPMENT_SYSTEM_PROMPT
from dosimeter.tools.dispatcher import InvocationRecord, Tool, ToolDispatcher
from dosimeter.workers.models import EquipmentProposal
from dosimeter.workers.toolsets import build_equipment_registry


def _equipment_proposal_from_invocations(
    invocations: list[InvocationRecord],
) -> EquipmentProposal:
    """Return the typed proposal produced by the Equipment Worker."""

    for invocation in reversed(invocations):
        if (
            invocation.tool == "propose_equipment_finding"
            and invocation.outcome == "ok"
            and invocation.result is not None
        ):
            return EquipmentProposal.model_validate(invocation.result)

    raise RuntimeError("Equipment Worker finished without producing a valid equipment proposal")


def run_equipment_worker(
    *,
    subject: Subject,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    prompt: str,
    max_iterations: int = 10,
) -> tuple[EquipmentProposal, list[InvocationRecord]]:
    """Run the Equipment Worker through the Bedrock tool loop."""

    registry = build_equipment_registry(
        shared_tools=shared_tools,
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        ledger=ledger,
        subject=subject,
    )

    run_tool_loop(
        prompt=prompt,
        system_prompt=EQUIPMENT_SYSTEM_PROMPT,
        tools=list(registry.values()),
        dispatcher=dispatcher,
        max_iterations=max_iterations,
    )

    proposal = _equipment_proposal_from_invocations(
        dispatcher.invocations,
    )

    return proposal, dispatcher.invocations
