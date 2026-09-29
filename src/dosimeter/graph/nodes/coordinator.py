"""Coordinator node.

The Coordinator decides which specialized workers should run.
The graph is responsible for routing the workers.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from dosimeter.graph.schemas import DispatchPlan
from dosimeter.graph.state import GraphState
from dosimeter.models.bedrock import get_chat_model
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


def coordinator_node(state: GraphState) -> dict:
    """Ask the model for a structured worker dispatch plan."""

    model = get_chat_model()

    structured_model = model.with_structured_output(DispatchPlan)

    prompt = _build_coordinator_prompt(state)

    plan = structured_model.invoke(
        [
            SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
    )

    if not isinstance(plan, DispatchPlan):
        plan = DispatchPlan.model_validate(plan)

    # This is important: don't allow the model to invent worker names.
    plan.validated_workers()

    return {
        "dispatch_plan": plan,
    }


def route_after_coordinator(state: GraphState) -> list[str]:
    """Route the graph to the workers selected by the Coordinator."""

    plan = state.get("dispatch_plan")

    if plan is None:
        return ["eligibility_check"]

    workers = plan.validated_workers()

    if not workers:
        return ["eligibility_check"]

    return workers
