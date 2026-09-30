"""Coordinator node.

The Coordinator decides which specialized workers should run.
The graph is responsible for routing the workers.
"""

import time

from langchain_core.messages import HumanMessage, SystemMessage

from dosimeter.graph.schemas import DispatchPlan
from dosimeter.graph.state import GraphState
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.models.bedrock import (
    REASONING_ROLE,
    check_budget,
    get_chat_model,
    max_tokens_for,
    record_usage,
)
from dosimeter.prompts import COORDINATOR_SYSTEM_PROMPT
from dosimeter.redaction import redact


def _build_coordinator_prompt(state: GraphState) -> str:
    """Build the Coordinator's input from the current graph state."""

    subject = state["subject"]

    prompt = f"""
        Analyze the current exposure run and decide which specialized workers
        are needed.

        Exposure ID: {subject.exposure_id}

        Current dispatch plan:
        {state.get("dispatch_plan")}

        Previous worker proposals:
        {state.get("proposals", [])}

        Previous reviewer verdicts:
        {state.get("reviewer_verdicts", [])}

        Reviewer iterations:
        {state.get("reviewer_iterations", 0)}

        If this is a redispatch after a Reviewer rejection, use the rejection
        reason to narrow the worker's next goal.

        Return only a DispatchPlan.
    """

    return redact(prompt)


def _rejection_trigger(state: GraphState) -> str | None:
    """The Reviewer rejections that sent this turn back for a re-dispatch."""

    iteration = state.get("reviewer_iterations", 0)
    rejected = [
        f"{verdict.worker}: {verdict.reason}"
        for verdict in state.get("reviewer_verdicts") or []
        if verdict.iteration == iteration and verdict.verdict == "rejected"
    ]

    return "; ".join(rejected) or None


def make_coordinator_node(
    *,
    ledger: SessionLedger | None = None,
    recorder: RunRecorder | None = None,
):
    """Create the Coordinator node, with the turn's budget and run record."""

    def coordinator_node(state: GraphState) -> dict:
        """Ask the model for a structured worker dispatch plan."""

        check_budget(ledger, "coordinator")

        model = get_chat_model(max_tokens=max_tokens_for(ledger, "coordinator"))

        # include_raw keeps the token usage next to the parsed plan
        structured_model = model.with_structured_output(DispatchPlan, include_raw=True)

        prompt = _build_coordinator_prompt(state)

        started = time.perf_counter()
        result = structured_model.invoke(
            [
                SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )

        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        record_usage(
            ledger=ledger,
            recorder=recorder,
            agent="coordinator",
            role=REASONING_ROLE,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            started=started,
        )

        plan = result.get("parsed")

        if plan is None:
            parsing_error = result.get("parsing_error")
            raw = result.get("raw")

            raise RuntimeError(
                "Coordinator failed to produce a valid DispatchPlan. "
                f"parsing_error={parsing_error!r}, raw={raw!r}"
            )

        if not isinstance(plan, DispatchPlan):
            plan = DispatchPlan.model_validate(plan)

        # This is important: don't allow the model to invent worker names.
        plan.validated_workers()

        # every dispatch lands on the run record; a re-dispatch names the rejection behind it
        if recorder is not None:
            iteration = state.get("reviewer_iterations", 0) + 1
            trigger = None
            if iteration > 1:
                trigger = plan.redispatch_trigger or _rejection_trigger(state)

            for worker in plan.validated_workers():
                recorder.dispatched(
                    worker,
                    plan.goals.get(worker, plan.rationale or "dispatched"),
                    iteration=iteration,
                    redispatch_trigger=trigger,
                )

        return {
            "dispatch_plan": plan,
        }

    return coordinator_node


def route_after_coordinator(state: GraphState) -> list[str]:
    """Route the graph to the workers selected by the Coordinator."""

    plan = state.get("dispatch_plan")

    if plan is None:
        return ["eligibility_check"]

    workers = plan.validated_workers()

    if not workers:
        return ["eligibility_check"]

    return workers
