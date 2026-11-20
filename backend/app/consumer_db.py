from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

from channels.db import database_sync_to_async

CONSUMER_DB_THREADS: int = 16
_consumer_db_executor = ThreadPoolExecutor(
    max_workers=CONSUMER_DB_THREADS, thread_name_prefix="ws-db"
)


def consumer_db[**P, R](func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """``database_sync_to_async`` on a pool instead of asgiref's one shared thread.

    Each call gets its own connection, closed after it (CONN_MAX_AGE=0), so a
    write waiting on SQLite's lock holds up only its own caller (#352).
    """
    return database_sync_to_async(
        func, thread_sensitive=False, executor=_consumer_db_executor
    )
