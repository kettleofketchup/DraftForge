from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from telemetry.logging import get_logger

log = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Module-level state for throttling
_last_request_time = 0.0
_request_lock: threading.Lock | None = None


def get_request_lock() -> threading.Lock:
    """Lazy initialization of threading lock."""
    global _request_lock
    if _request_lock is None:
        _request_lock = threading.Lock()
    return _request_lock


def throttle_request(
    min_delay: float = 0.5,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that ensures minimum delay between Steam API requests.
    Steam API limit is 1 request per second; we use 0.5s for safety margin.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            global _last_request_time
            lock = get_request_lock()

            with lock:
                current_time = time.time()
                elapsed = current_time - _last_request_time
                if elapsed < min_delay:
                    sleep_time = min_delay - elapsed
                    time.sleep(sleep_time)
                _last_request_time = time.time()

            return func(*args, **kwargs)

        return wrapper

    return decorator


def retry_with_backoff(
    func: Callable[[], T], max_retries: int = 3, base_delay: float = 1.0
) -> tuple[bool, T | Exception | None]:
    """
    Retry a function with exponential backoff.

    Args:
        func: Callable to execute
        max_retries: Maximum number of attempts
        base_delay: Initial delay in seconds (doubles each retry)

    Returns:
        tuple: (success: bool, result_or_error)
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            result = func()
            return (True, result)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                log.warning(
                    "retry_attempt_failed",
                    system="steam",
                    subsystem="retry",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                time.sleep(delay)

    return (False, last_exception)
