"""Logging. Each line is written as JSON and tagged with the id of the
request that caused it, so lines from one run can be pulled back together."""

import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from dosimeter.redaction import redact

# a contextvar, so two turns running at the same time never see each other's id
CORRELATION_ID: ContextVar[str] = ContextVar("correlation_id", default="-")

# every log record has these; anything else on a record came in through extra={...}
STANDARD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}

HANDLER_NAME = "dosimeter-json"


def get_correlation_id() -> str:
    """The id of the request we are handling right now."""

    return CORRELATION_ID.get()


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Use this id inside the block, then put back whatever was there before."""

    value = correlation_id or uuid.uuid4().hex
    token = CORRELATION_ID.set(value)
    try:
        yield value
    finally:
        CORRELATION_ID.reset(token)


class JsonFormatter(logging.Formatter):
    """Turn a log line into one line of JSON, with names and dose histories taken out."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        for key, value in record.__dict__.items():
            if key not in STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(redact(payload), default=str, sort_keys=True)


def configure_logging(level: int | str = logging.INFO) -> None:
    """Set up logging. Calling it twice does no harm."""

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.set_name(HANDLER_NAME)

    # swap out our own handler from an earlier call, and leave any others alone
    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
