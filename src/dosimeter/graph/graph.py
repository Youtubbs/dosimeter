""" The graph: a Coordinator, three workers, a Reviewer and the eligibility check """

from langgraph.graph import END, START, StateGraph

from dosimeter.config.settings import Bounds
from dosimeter.graph.nodes.coordinator import coordinator_node, route_after_coordinator
from dosimeter.graph.nodes.eligibility import eligibility_node
from dosimeter.graph.nodes.reviewer import reviewer_node, route_after_reviewer
from dosimeter.graph.nodes.workers import equipment_node, notification_node, written_report_node
from dosimeter.graph.schemas import WORKER_NAMES
from dosimeter.graph.state import GraphState


# checkpointer writes graph state to Postgres, one thread per participant
#   PostgresSaver - see graph/checkpointer.py
#       https://docs.langchain.com/oss/python/langgraph/persistence
def build_graph(bounds: Bounds, checkpointer=None):

    graph = StateGraph(GraphState)

    # --- NODES ---
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("notification", notification_node)
    graph.add_node("written_report", written_report_node)
    graph.add_node("equipment", equipment_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("eligibility_check", eligibility_node)

    # --- EDGES ---
    graph.add_edge(START, "coordinator")

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
