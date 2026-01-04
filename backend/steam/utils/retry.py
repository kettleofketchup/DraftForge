import logging
import time

log = logging.getLogger(__name__)


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
                    f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                time.sleep(delay)

    return (False, last_exception)
