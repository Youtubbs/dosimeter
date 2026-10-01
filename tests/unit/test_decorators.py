"""The retry decorator works, and a decorated function keeps its own name."""

import random

import pytest

from dosimeter.decorators import retry
from dosimeter.errors import ExternalServiceError


@retry(attempts=3, base_delay=0.0, sleep=lambda _: None)
def flaky(counter: list[int]) -> str:
    """Fail twice, then succeed."""

    counter.append(1)
    if len(counter) < 3:
        raise ExternalServiceError("throttled")
    return "ok"


def test_retry_preserves_name_and_docstring() -> None:
    assert flaky.__name__ == "flaky"
    assert flaky.__doc__ == "Fail twice, then succeed."


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
