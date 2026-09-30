"""LangGraph worker-node builders."""

from collections.abc import Iterable

from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.tools.dispatcher import Tool
from dosimeter.workers.nodes import (
    make_equipment_node,
    make_notification_node,
    make_written_report_node,
)


def build_notification_node(
    *,
    ledger: SessionLedger,
    shared_tools: Iterable[Tool],
    recorder: RunRecorder | None = None,
):
    """Build the LangGraph Notification Worker node."""

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
    """Build the LangGraph Written Report Worker node."""

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
