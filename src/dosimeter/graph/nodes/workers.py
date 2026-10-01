"""The three workers. Each one is given a single question to answer"""

from collections.abc import Iterable

from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.tools.dispatcher import Tool
from dosimeter.workers.nodes import make_equipment_node, make_notification_node, make_written_report_node


def build_notification_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    recorder: RunRecorder | None = None,
):
    """Does any 20.2202 tier fire, and on what clock?"""

    return make_notification_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )


def build_written_report_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    recorder: RunRecorder | None = None,
):
    """Is a 20.2203 report owed, or does 20.1206 except the dose and substitute 20.2204?"""

    return make_written_report_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )


def build_equipment_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    recorder: RunRecorder | None = None,
):
    """Build the LangGraph Equipment Worker node."""

    return make_equipment_node(
        ledger=ledger,
        shared_tools=shared_tools,
        recorder=recorder,
    )
