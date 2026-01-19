import logging
import time
from functools import wraps

log = logging.getLogger(__name__)

# Module-level state for throttling
_last_request_time = 0.0
_request_lock = None


def get_request_lock():
    """Lazy initialization of threading lock."""
    global _request_lock
    if _request_lock is None:
        import threading

        _request_lock = threading.Lock()
    return _request_lock


def throttle_request(min_delay: float = 0.5):
    """
    Decorator that ensures minimum delay between Steam API requests.
    Steam API limit is 1 request per second; we use 0.5s for safety margin.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
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
