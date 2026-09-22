"""Logging. Each line is written as JSON and tagged with the id of the
request that caused it, so lines from one run can be pulled back together."""

from __future__ import annotations

import contextlib
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

CORRELATION_ID: ContextVar[str] = ContextVar("correlation_id", default="-")

_HANDLER_NAME = "dosimeter-json"

_RESERVED_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "correlation_id",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def get_correlation_id() -> str:
    """The id of the request we are handling right now."""

    return CORRELATION_ID.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the id for the request we are handling right now."""

    CORRELATION_ID.set(correlation_id)


def new_correlation_id() -> str:
    """Make up a new id."""

    return uuid.uuid4().hex


@contextlib.contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Use this id inside the block, then put back whatever was there before."""

    value = correlation_id or new_correlation_id()
    token = CORRELATION_ID.set(value)
    try:
        yield value
    finally:
        CORRELATION_ID.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Stamp the current id onto each log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


class JsonFormatter(logging.Formatter):
    """Turn a log line into one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", get_correlation_id()),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: int | str = logging.INFO) -> None:
    """Set up logging. Calling it twice does no harm."""

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    handler.set_name(_HANDLER_NAME)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == _HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger that stamps the request id on every line."""

    logger = logging.getLogger(name)
    if not any(isinstance(item, CorrelationIdFilter) for item in logger.filters):
        logger.addFilter(CorrelationIdFilter())
    return logger


__all__ = [
    "CORRELATION_ID",
    "CorrelationIdFilter",
    "JsonFormatter",
    "configure_logging",
    "correlation_scope",
    "get_correlation_id",
    "get_logger",
    "new_correlation_id",
    "set_correlation_id",
]
