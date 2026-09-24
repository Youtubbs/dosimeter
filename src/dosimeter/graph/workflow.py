"""
The graph topology: a Coordinator that dispatches nothing to three workers,
parallel legs that merge into a Reviewer, a rejection cycle back to the
Coordinator, and an eligibility check on the way out.

The node bodies are supplied by the caller. This module owns the shape, the
routing and the caps, which are plain Python and unit-testable without a model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from langgraph.graph import END, START, StateGraph

from dosimeter.config.settings import Bounds
from dosimeter.graph.state import GraphState

NodeFn = Callable[[GraphState], dict]

COORDINATOR = "coordinator"
REVIEWER = "reviewer"
ELIGIBILITY = "eligibility_check"
WORKER_NODES = ("notification", "written_report", "equipment")

APPROVED = "approved"
REJECTED = "rejected"


def _noop(state: GraphState) -> dict:
    return {}


@dataclass
class Nodes:
    """The work each node does. Defaults do nothing, so the shape can be tested."""

    coordinator: NodeFn = _noop
    notification: NodeFn = _noop
    written_report: NodeFn = _noop
    equipment: NodeFn = _noop
    reviewer: NodeFn = _noop
    eligibility_check: NodeFn = _noop
    extra: dict[str, NodeFn] = field(default_factory=dict)


def route_after_coordinator(state: GraphState) -> list[str]:
    """Where the dispatch plan sends this turn. No plan means nothing to review."""

    plan = state.get("dispatch_plan")
    if plan is None:
        return [ELIGIBILITY]

    workers = plan.validated_workers()
    if not workers:
        return [ELIGIBILITY]

    return workers


def route_after_reviewer(state: GraphState, bounds: Bounds) -> str:
    """
    A rejection goes back to the Coordinator until the iteration cap stops it.
    The cap is the backstop; the verdict is the condition.
    """

    verdicts = state.get("reviewer_verdicts") or []
    iterations = state.get("reviewer_iterations", 0)

    if iterations >= bounds.reviewer_iteration_cap:
        return ELIGIBILITY

    if verdicts and verdicts[-1].verdict == REJECTED:
        return COORDINATOR

    return ELIGIBILITY


def build_graph(nodes: Nodes, bounds: Bounds) -> StateGraph:
    """Wire the topology. Compile it with a checkpointer to run it."""

    graph = StateGraph(GraphState)

    graph.add_node(COORDINATOR, nodes.coordinator)
    graph.add_node("notification", nodes.notification)
    graph.add_node("written_report", nodes.written_report)
    graph.add_node("equipment", nodes.equipment)
    graph.add_node(REVIEWER, nodes.reviewer)
    graph.add_node(ELIGIBILITY, nodes.eligibility_check)
    for name, node in nodes.extra.items():
        graph.add_node(name, node)

    graph.add_edge(START, COORDINATOR)
    graph.add_conditional_edges(
        COORDINATOR,
        route_after_coordinator,
        [*WORKER_NODES, ELIGIBILITY],
    )

    for worker in WORKER_NODES:
        graph.add_edge(worker, REVIEWER)

    graph.add_conditional_edges(
        REVIEWER,
        lambda state: route_after_reviewer(state, bounds),
        [COORDINATOR, ELIGIBILITY],
    )
    graph.add_edge(ELIGIBILITY, END)

    return graph


def compile_graph(nodes: Nodes, bounds: Bounds, checkpointer=None):
    """A compiled graph, checkpointed when a saver is given."""

    return build_graph(nodes, bounds).compile(checkpointer=checkpointer)
