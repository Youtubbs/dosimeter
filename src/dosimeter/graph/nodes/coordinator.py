""" The Coordinator: decides which workers this exposure needs """

from dosimeter.graph.state import GraphState


def coordinator_node(state: GraphState) -> dict:
    """
    Plans the turn. The Coordinator's Bedrock call goes here and returns a
    DispatchPlan. Until it is written the plan stays empty, so the turn goes
    straight to the eligibility check.
    """

    return {}


def route_after_coordinator(state: GraphState) -> list[str]:
    """Where the dispatch plan sends this turn. No plan means nothing to review."""

    plan = state.get("dispatch_plan")
    if plan is None:
        return ["eligibility_check"]

    workers = plan.validated_workers()
    if not workers:
        return ["eligibility_check"]

    # returning a list starts every named worker at once, so the legs run concurrently
    return workers
