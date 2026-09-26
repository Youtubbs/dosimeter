""" Decorators the rest of the code reuses """

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def retry(
    attempts: int = 3,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    jitter: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
):
    """
    Try the call again if it fails, waiting a bit longer each time. If the last
    try still fails, that error is passed straight on to the caller.

    The wait doubles after each failure, up to max_delay, plus a little
    randomness so two callers do not retry at the same moment.
    """

    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    random_source = rng or random.Random()  # noqa: S311 

    def decorator(func):
        # functools.wraps keeps the wrapped function's name and docstring
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on:
                    if attempt == attempts:
                        raise

                    delay = min(base_delay * 2 ** (attempt - 1), max_delay)
                    spread = delay * jitter
                    delay = max(0.0, delay + random_source.uniform(-spread, spread))

                    logger.warning(
                        "call.retry",
                        extra={
                            "call": func.__qualname__,
                            "attempt": attempt,
                            "delay_seconds": round(delay, 3),
                        },
                    )
                    sleep(delay)

        return wrapper

    return decorator
