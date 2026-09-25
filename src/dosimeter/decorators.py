"""Decorators the rest of the code reuses: time a call, retry a call, and
keep a note of what a call did."""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

from dosimeter.errors import DosimeterError
from dosimeter.logging_config import get_correlation_id, get_logger

F = TypeVar("F", bound=Callable[..., Any])

_LOGGER = get_logger(__name__)

RUN_EVENTS: ContextVar[tuple[dict[str, Any], ...]] = ContextVar("run_events", default=())


def record_event(event: dict[str, Any]) -> None:
    """Add one event to the list we are keeping for this run."""

    RUN_EVENTS.set((*RUN_EVENTS.get(), event))


def get_run_events() -> tuple[dict[str, Any], ...]:
    """The events for this run, oldest first."""

    return RUN_EVENTS.get()


@contextmanager
def run_event_scope() -> Iterator[Callable[[], tuple[dict[str, Any], ...]]]:
    """Keep a fresh list of events for the block, then throw it away."""

    token = RUN_EVENTS.set(())
    try:
        yield get_run_events
    finally:
        RUN_EVENTS.reset(token)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def timed(func: F) -> F:
    """Log how long the call took."""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                _LOGGER.info(
                    "call.timed",
                    extra={"call": func.__qualname__, "duration_ms": _elapsed_ms(started)},
                )

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            _LOGGER.info(
                "call.timed",
                extra={"call": func.__qualname__, "duration_ms": _elapsed_ms(started)},
            )

    return wrapper  # type: ignore[return-value]


def _backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
    rng: random.Random,
) -> float:
    """How long to wait before the next try. Doubles each time, plus a little
    randomness so two callers do not retry at the same moment."""

    delay = min(base_delay * (2**attempt), max_delay)
    spread = delay * jitter
    return max(0.0, delay + rng.uniform(-spread, spread))


def retry(
    attempts: int = 3,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    jitter: float = 0.25,
    sleep: Callable[[float], None] | None = None,
    rng: random.Random | None = None,
) -> Callable[[F], F]:
    """
    Try the call again if it fails, waiting a bit longer each time. If the last
    try still fails, that error is passed straight on to the caller.
    """

    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorate(func: F) -> F:
        random_source = rng or random.Random()  # noqa: S311

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                for attempt in range(attempts):
                    try:
                        return await func(*args, **kwargs)
                    except retry_on:
                        if attempt == attempts - 1:
                            raise
                        delay = _backoff_delay(
                            attempt, base_delay, max_delay, jitter, random_source
                        )
                        _LOGGER.warning(
                            "call.retry",
                            extra={
                                "call": func.__qualname__,
                                "attempt": attempt + 1,
                                "delay_seconds": round(delay, 3),
                            },
                        )
                        await asyncio.sleep(delay)
                raise AssertionError("unreachable")

            return async_wrapper  # type: ignore[return-value]

        sleep_for = sleep or time.sleep

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on:
                    if attempt == attempts - 1:
                        raise
                    delay = _backoff_delay(attempt, base_delay, max_delay, jitter, random_source)
                    _LOGGER.warning(
                        "call.retry",
                        extra={
                            "call": func.__qualname__,
                            "attempt": attempt + 1,
                            "delay_seconds": round(delay, 3),
                        },
                    )
                    sleep_for(delay)
            raise AssertionError("unreachable")

        return wrapper  # type: ignore[return-value]

    return decorate


def _event(name: str, started: float, outcome: str, error: BaseException | None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event": name,
        "outcome": outcome,
        "duration_ms": _elapsed_ms(started),
        "correlation_id": get_correlation_id(),
    }
    if error is not None:
        event["error_type"] = type(error).__name__
        event["dosimeter_error"] = isinstance(error, DosimeterError)
    return event


def captures_run_event(event_name: str | None = None) -> Callable[[F], F]:
    """Note down what the call did, whether it worked or not."""

    def decorate(func: F) -> F:
        name = event_name or func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except BaseException as error:
                    record_event(_event(name, started, "error", error))
                    raise
                record_event(_event(name, started, "ok", None))
                return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except BaseException as error:
                record_event(_event(name, started, "error", error))
                raise
            record_event(_event(name, started, "ok", None))
            return result

        return wrapper  # type: ignore[return-value]

    return decorate


__all__ = [
    "RUN_EVENTS",
    "captures_run_event",
    "get_run_events",
    "record_event",
    "retry",
    "run_event_scope",
    "timed",
]
