""" The Dossier Reviewer, and the cycle back to the Coordinator when it rejects """

from dosimeter.graph.state import GraphState


def reviewer_node(state: GraphState) -> dict:
    """Grounded? Cited? Attributed? Resting on a proposed rule? Not written yet."""

    return {}


def route_after_reviewer(state: GraphState, iteration_cap: int) -> str:
    """
    A rejection goes back to the Coordinator until the iteration cap stops it.
    The cap is the backstop; the verdict is the condition.
    """

    verdicts = state.get("reviewer_verdicts") or []
    iterations = state.get("reviewer_iterations", 0)

    if iterations >= iteration_cap:
        return "eligibility_check"

    if verdicts and verdicts[-1].verdict == "rejected":
        return "coordinator"

    return "eligibility_check"
