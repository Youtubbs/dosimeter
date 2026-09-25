"""
Where the graph gets its node bodies and its escalation evaluator.

The Coordinator, the three workers and the Reviewer belong to the other two
streams. This module is the seam: it hands the graph whatever has been
registered, and an empty registration still runs a turn and writes a record.
"""

from __future__ import annotations

from collections.abc import Callable

from dosimeter.config.settings import Settings
from dosimeter.graph.workflow import Nodes
from dosimeter.harness.escalation import EscalationOutcome, Evaluator, TriggerSignals

NodesFactory = Callable[[Settings], Nodes]
EvaluatorFactory = Callable[[], Evaluator]

_NODES: NodesFactory | None = None
_EVALUATOR: EvaluatorFactory | None = None


def register_nodes(factory: NodesFactory) -> None:
    """Called by the module that owns the Coordinator, workers and Reviewer."""

    global _NODES
    _NODES = factory


def register_evaluator(factory: EvaluatorFactory) -> None:
    """Called by the module that owns the escalation triggers."""

    global _EVALUATOR
    _EVALUATOR = factory


def build_nodes(settings: Settings) -> Nodes:
    if _NODES is None:
        return Nodes()
    return _NODES(settings)


def _nothing_fired(signals: TriggerSignals) -> EscalationOutcome:
    """
    Stands in until the real evaluator is registered. It fires nothing, which
    is visible in the run record as a turn where no trigger was evaluated.
    """

    return EscalationOutcome(evaluated=[], fired=[])


def escalation_evaluator() -> Evaluator:
    if _EVALUATOR is None:
        return _nothing_fired
    return _EVALUATOR()
