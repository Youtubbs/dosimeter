"""The graph: a Coordinator, three workers, a Reviewer and the eligibility check"""

from langgraph.graph import END, START, StateGraph

from dosimeter.config.settings import Bounds
from dosimeter.graph.nodes.coordinator import make_coordinator_node, route_after_coordinator
from dosimeter.graph.nodes.eligibility import eligibility_node, route_on_readiness
from dosimeter.graph.nodes.reviewer import make_reviewer_node, route_after_reviewer
from dosimeter.graph.nodes.workers import (
    build_equipment_node,
    build_notification_node,
    build_written_report_node,
)
from dosimeter.graph.schemas import WORKER_NAMES
from dosimeter.graph.state import GraphState
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.tools.tools import Tool
from collections.abc import Iterable


# checkpointer writes graph state to Postgres, one thread per participant
#   PostgresSaver - see graph/checkpointer.py
#       https://docs.langchain.com/oss/python/langgraph/persistence
def build_graph(
    bounds: Bounds,
    *,
    ledger: SessionLedger | None = None,
    recorder: RunRecorder | None = None,
    shared_tools: Iterable[Tool] = (),
    checkpointer=None,
):

    graph = StateGraph(GraphState)

    # --- NODES ---
    # every node that calls a model checks the ledger first and records what it spent
    graph.add_node("coordinator", make_coordinator_node(ledger=ledger, recorder=recorder))
    workers = {"ledger": ledger, "shared_tools": list(shared_tools), "recorder": recorder}
    graph.add_node("notification", build_notification_node(**workers))
    graph.add_node("written_report", build_written_report_node(**workers))
    graph.add_node("equipment", build_equipment_node(**workers))
    graph.add_node("reviewer", make_reviewer_node(ledger=ledger, recorder=recorder))
    graph.add_node("eligibility_check", eligibility_node)

    # --- EDGES ---
    # the readiness gate can stop a turn before dispatch, never start one
    graph.add_conditional_edges(START, route_on_readiness, ["coordinator", "eligibility_check"])

    # the model chooses what, the graph routes it: 0 to 3 workers from the dispatch plan
    graph.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        [*WORKER_NAMES, "eligibility_check"],
    )

    # every worker leads to the Reviewer, which runs once the dispatched legs finish
    for worker in WORKER_NAMES:
        graph.add_edge(worker, "reviewer")

    # a rejection loops back to the Coordinator; the iteration cap from settings ends the loop
    graph.add_conditional_edges(
        "reviewer",
        lambda state: route_after_reviewer(state, bounds.reviewer_iteration_cap),
        ["coordinator", "eligibility_check"],
    )

    graph.add_edge("eligibility_check", END)

    return graph.compile(checkpointer=checkpointer)
