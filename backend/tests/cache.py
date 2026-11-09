"""Cache reset for test processes, scoped to this run's Redis namespace.

cacheops' invalidate_all() is FLUSHDB on DB 1, which the running test stack
also uses for its cache and Celery broker; this deletes only this run's keys.
"""

import re

from cacheops.redis import redis_client
from django.conf import settings

_GLOB_SPECIAL = re.compile(r"([*?\[\]\\])")


def _glob_prefix(prefix: str) -> str:
    return _GLOB_SPECIAL.sub(r"\\\1", prefix) + "*"


def flush_run_cache() -> int:
    """Delete this run's cacheops and Django cache keys; return how many."""
    namespace: str = getattr(settings, "REDIS_KEY_NAMESPACE", "")
    if not namespace:
        raise RuntimeError("flush_run_cache() needs a test-run REDIS_KEY_NAMESPACE")
    deleted = 0
    for prefix in (settings.CACHEOPS_PREFIX(None), namespace):
        batch: list[bytes] = []
        for key in redis_client.scan_iter(match=_glob_prefix(prefix), count=500):
            batch.append(key)
            if len(batch) >= 500:
                deleted += redis_client.delete(*batch)
                batch.clear()
        if batch:
            deleted += redis_client.delete(*batch)
    return deleted
