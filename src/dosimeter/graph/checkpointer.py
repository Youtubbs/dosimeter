"""
The LangGraph checkpointer, pointed at the same Postgres the application uses.

Verified against langgraph 1.2.11 and langgraph-checkpoint-postgres 3.1.2:
PostgresSaver.from_conn_string is a context manager, and setup() creates the
checkpoint tables.
"""

import importlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from dosimeter.config.settings import DatabaseSettings
from dosimeter.repository.connection import conn_string

# the modules whose models and enums travel in graph state
STATE_MODULES = (
    "dosimeter.graph.schemas",
    "dosimeter.harness.escalation",
    "dosimeter.guardrails.events",
    "dosimeter.domain.rules",
    "dosimeter.domain.dose",
    "dosimeter.workers.models",
    "dosimeter.rules.r3_written_report",
    "dosimeter.rules.r4_planned_special_exposure",
    "dosimeter.rules.r5_confidence",
)


def state_types() -> list[tuple[str, str]]:
    """Every model and enum those modules define, so LangGraph may read them back out of a checkpoint."""

    types = []
    for name in STATE_MODULES:
        for attr, value in vars(importlib.import_module(name)).items():
            if isinstance(value, type) and value.__module__ == name and issubclass(value, (BaseModel, Enum)):
                types.append((name, attr))
    return types


@contextmanager
def open_checkpointer(
    settings: DatabaseSettings | None = None,
    token_provider: Callable[[], str] | None = None,
) -> Iterator[PostgresSaver]:
    """Open a checkpointer against the application database."""

    with PostgresSaver.from_conn_string(conn_string(settings, token_provider)) as saver:
        saver.serde = JsonPlusSerializer(allowed_msgpack_modules=state_types())
        yield saver


def setup_checkpointer(
    settings: DatabaseSettings | None = None,
    token_provider: Callable[[], str] | None = None,
) -> None:
    """Create the checkpoint tables. Safe to run more than once."""

    with open_checkpointer(settings, token_provider) as saver:
        saver.setup()
