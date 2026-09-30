"""The graph: a Coordinator, three workers, a Reviewer and the eligibility check."""

from collections.abc import Iterable

from langgraph.graph import END, START, StateGraph

from dosimeter.config.settings import Bounds
from dosimeter.graph.nodes.coordinator import make_coordinator_node, route_after_coordinator
from dosimeter.graph.nodes.eligibility import eligibility_node
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


# Checkpointer writes graph state to Postgres, one thread per participant.
# PostgresSaver - see graph/checkpointer.py
# https://docs.langchain.com/oss/python/langgraph/persistence
def build_graph(
    bounds: Bounds,
    *,
    ledger: SessionLedger | None = None,
    recorder: RunRecorder | None = None,
    shared_tools: Iterable[Tool] = (),
    checkpointer=None,
):
    """Build and compile the Dosimeter workflow graph."""

    graph = StateGraph(GraphState)

    # --- NODES ---
    # Every node that calls a model checks the ledger first and records
    # what it spent.
    graph.add_node(
        "coordinator",
        make_coordinator_node(
            ledger=ledger,
            recorder=recorder,
        ),
    )

    notification_node = build_notification_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )
    graph.add_node("notification", notification_node)

    written_report_node = build_written_report_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )
    graph.add_node("written_report", written_report_node)

    equipment_node = build_equipment_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )
    graph.add_node("equipment", equipment_node)

    graph.add_node(
        "reviewer",
        make_reviewer_node(
            ledger=ledger,
            recorder=recorder,
        ),
    )

    graph.add_node("eligibility_check", eligibility_node)

    # --- EDGES ---
    graph.add_edge(START, "coordinator")

    # The model chooses what; the graph routes it:
    # 0 to 3 workers from the dispatch plan.
    graph.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        [*WORKER_NAMES, "eligibility_check"],
    )

    # Every worker leads to the Reviewer, which runs once the
    # dispatched legs finish.
    for worker in WORKER_NAMES:
        graph.add_edge(worker, "reviewer")

    # A rejection loops back to the Coordinator; the iteration cap
    # from settings ends the loop.
    graph.add_conditional_edges(
        "reviewer",
        lambda state: route_after_reviewer(
            state,
            bounds.reviewer_iteration_cap,
        ),
        ["coordinator", "eligibility_check"],
    )

    graph.add_edge("eligibility_check", END)

    return graph.compile(checkpointer=checkpointer)
