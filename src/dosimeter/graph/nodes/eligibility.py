""" The eligibility check at the end of every turn """

from dosimeter.graph.state import GraphState
from dosimeter.harness.escalation import TriggerSignals, evaluate


def signals_from_state(state: GraphState) -> TriggerSignals:
    """Read the turn's own record out of graph state. No model opinion here."""

    verdicts = state.get("reviewer_verdicts") or []
    return TriggerSignals(
        reviewer_iterations=state.get("reviewer_iterations", 0),
        reviewer_approved=bool(verdicts) and verdicts[-1].verdict == "approved",
    )


def eligibility_node(state: GraphState) -> dict:
    """
    Decide from deterministic signals whether the dossier stands or goes to a
    person. The harness records the result and queues the dossier.
    """

    escalation = evaluate(signals_from_state(state))
    return {
        "escalation": escalation,
        "outcome": "escalated" if escalation.escalates else "ready_for_officer",
    }
