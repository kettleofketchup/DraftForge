import time

from telemetry.logging import get_logger

log = get_logger(__name__)


def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """
    Retry a function with exponential backoff.

    Args:
        func: Callable to execute
        max_retries: Maximum number of attempts
        base_delay: Initial delay in seconds (doubles each retry)

    Returns:
        tuple: (success: bool, result_or_error)
    """
    last_exception = None

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
