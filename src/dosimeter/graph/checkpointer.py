"""
The LangGraph checkpointer, pointed at the same Postgres the application uses.

Verified against langgraph 1.2.11 and langgraph-checkpoint-postgres 3.1.2:
PostgresSaver.from_conn_string is a context manager, and setup() creates the
checkpoint tables.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from dosimeter.config.settings import DatabaseSettings
from dosimeter.repository.connection import conn_string


@contextmanager
def open_checkpointer(
    settings: DatabaseSettings | None = None,
    token_provider: Callable[[], str] | None = None,
) -> Iterator[PostgresSaver]:
    """Open a checkpointer against the application database."""

    with PostgresSaver.from_conn_string(conn_string(settings, token_provider)) as saver:
        yield saver


def setup_checkpointer(
    settings: DatabaseSettings | None = None,
    token_provider: Callable[[], str] | None = None,
) -> None:
    """Create the checkpoint tables. Safe to run more than once."""

    with open_checkpointer(settings, token_provider) as saver:
        saver.setup()
