""" The three workers. Each one is given a single question to answer """

from dosimeter.graph.state import GraphState
from dosimeter.workers.nodes import make_equipment_node


def notification_node(state: GraphState) -> dict:
    """Does any 20.2202 tier fire, and on what clock? Not written yet."""

    return {}


def written_report_node(state: GraphState) -> dict:
    """Is a 20.2203 report owed, or does 20.1206 except the dose and substitute 20.2204? Not written yet."""

    return {}


def build_equipment_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
):
    """Build the LangGraph Equipment Worker node."""

    return make_equipment_node(
        ledger=ledger,
        shared_tools=shared_tools,
    )
