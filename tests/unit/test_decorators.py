"""The decorators work, and a decorated function keeps its own name."""

from __future__ import annotations

import random

import pytest

from dosimeter.decorators import (
    captures_run_event,
    get_run_events,
    retry,
    run_event_scope,
    timed,
)
from dosimeter.errors import ExternalServiceError
from dosimeter.logging_config import correlation_scope


@timed
def submit_packet(exposure_id: str) -> str:
    """Pretend to submit a packet."""

    return exposure_id


@retry(attempts=3, base_delay=0.0, sleep=lambda _: None)
def flaky(counter: list[int]) -> str:
    """Fail twice, then succeed."""

    counter.append(1)
    if len(counter) < 3:
        raise ExternalServiceError("throttled")
    return "ok"


@captures_run_event("rules.apply")
def apply_rules(outcome: str) -> str:
    """Pretend to apply a rule."""

    if outcome == "boom":
        raise ExternalServiceError("upstream down")
    return outcome


def test_timed_preserves_name_and_docstring() -> None:
    assert submit_packet.__name__ == "submit_packet"
    assert submit_packet.__doc__ == "Pretend to submit a packet."
    assert submit_packet("exp-0411") == "exp-0411"


def test_retry_preserves_name_and_docstring() -> None:
    assert flaky.__name__ == "flaky"
    assert flaky.__doc__ == "Fail twice, then succeed."


def test_capture_preserves_name_and_docstring() -> None:
    assert apply_rules.__name__ == "apply_rules"
    assert apply_rules.__doc__ == "Pretend to apply a rule."


def test_retry_succeeds_after_transient_failures() -> None:
    attempts: list[int] = []

    assert flaky(attempts) == "ok"
    assert len(attempts) == 3


def test_retry_reraises_the_last_failure() -> None:
    delays: list[float] = []

    @retry(attempts=3, base_delay=0.1, jitter=0.0, sleep=delays.append)
    def always_fails() -> None:
        raise ExternalServiceError("still down")

    with pytest.raises(ExternalServiceError):
        always_fails()

    assert delays == [0.1, 0.2]


def test_retry_does_not_swallow_an_unlisted_exception() -> None:
    calls: list[int] = []

    @retry(attempts=3, retry_on=(ExternalServiceError,), base_delay=0.0, sleep=lambda _: None)
    def wrong_kind() -> None:
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        wrong_kind()

    assert len(calls) == 1


def test_backoff_is_capped_and_jittered() -> None:
    delays: list[float] = []

    @retry(
        attempts=4,
        base_delay=1.0,
        max_delay=2.0,
        jitter=0.5,
        sleep=delays.append,
        rng=random.Random(7),  # noqa: S311
    )
    def always_fails() -> None:
        raise ExternalServiceError("still down")

    with pytest.raises(ExternalServiceError):
        always_fails()

    assert len(delays) == 3
    assert all(0.0 <= delay <= 3.0 for delay in delays)
    assert len(set(delays)) > 1


def test_rejects_a_zero_attempt_policy() -> None:
    with pytest.raises(ValueError):
        retry(attempts=0)


def test_run_events_capture_success_and_failure() -> None:
    with correlation_scope("run-1"), run_event_scope() as events:
        apply_rules("clear")

        with pytest.raises(ExternalServiceError):
            apply_rules("boom")

        captured = events()

    assert [item["outcome"] for item in captured] == ["ok", "error"]
    assert captured[0]["event"] == "rules.apply"
    assert captured[0]["correlation_id"] == "run-1"
    assert captured[1]["error_type"] == "ExternalServiceError"
    assert captured[1]["dosimeter_error"] is True


def test_run_events_do_not_escape_their_scope() -> None:
    with run_event_scope():
        apply_rules("clear")

    assert get_run_events() == ()


@pytest.mark.asyncio
async def test_async_decorators_work_and_preserve_metadata() -> None:
    @timed
    @captures_run_event("ask.answer")
    @retry(attempts=2, base_delay=0.0)
    async def answer(question: str) -> str:
        """Pretend to answer a question."""

        return question.upper()

    with run_event_scope() as events:
        assert await answer("what is tede") == "WHAT IS TEDE"
        captured = events()

    assert answer.__name__ == "answer"
    assert answer.__doc__ == "Pretend to answer a question."
    assert [item["event"] for item in captured] == ["ask.answer"]
