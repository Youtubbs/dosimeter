"""Log lines carry the request id, and two requests never mix them up."""

import asyncio
import json
import logging

import pytest

from dosimeter.logging_config import (
    JsonFormatter,
    configure_logging,
    correlation_scope,
    get_correlation_id,
)


def _render(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="dosimeter.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_log_line_is_one_json_object() -> None:
    line = JsonFormatter().format(_record("packet.submitted"))

    assert "\n" not in line
    assert json.loads(line)["message"] == "packet.submitted"


def test_correlation_id_is_attached_without_the_call_site_passing_it() -> None:
    with correlation_scope("abc123"):
        payload = _render(_record("rules.invoked"))

    assert payload["correlation_id"] == "abc123"


def test_extra_fields_survive_into_the_payload() -> None:
    with correlation_scope("abc123"):
        payload = _render(_record("call.retry", call="submit", delay_seconds=0.2))

    assert payload["call"] == "submit"
    assert payload["delay_seconds"] == 0.2


def test_correlation_scope_restores_the_previous_value() -> None:
    with correlation_scope("outer"):
        with correlation_scope("inner"):
            assert get_correlation_id() == "inner"

        assert get_correlation_id() == "outer"


def test_a_scope_without_an_id_makes_a_new_one() -> None:
    with correlation_scope() as first, correlation_scope() as second:
        assert first != second


def test_configure_logging_installs_exactly_one_json_handler() -> None:
    configure_logging(logging.DEBUG)
    configure_logging(logging.DEBUG)

    json_handlers = [
        item for item in logging.getLogger().handlers if isinstance(item.formatter, JsonFormatter)
    ]
    assert len(json_handlers) == 1


@pytest.mark.asyncio
async def test_correlation_id_does_not_leak_between_concurrent_tasks() -> None:
    seen: dict[str, str] = {}

    async def turn(name: str, correlation_id: str, pause: float) -> None:
        with correlation_scope(correlation_id):
            await asyncio.sleep(pause)
            seen[name] = get_correlation_id()

    with correlation_scope("main-turn"):
        await asyncio.gather(
            turn("first", "turn-one", 0.02),
            turn("second", "turn-two", 0.01),
        )

        assert get_correlation_id() == "main-turn"

    assert seen == {"first": "turn-one", "second": "turn-two"}
