"""Populate's cache flush drops cached queries but leaves live draft Redis state alone."""

from collections.abc import Iterator
from datetime import date
from unittest.mock import patch

from cacheops.redis import redis_client as cacheops_redis
from django.conf import settings
from django.test import TransactionTestCase

from app.models import Tournament
from app.tasks.draft_tick import (
    conn_count_key,
    get_connection_count,
    get_redis_client,
    heartbeat_key,
    increment_connection_count,
)
from tests.populate.utils import flush_redis_cache
from user.tests.test_cacheops_integration import _redis_reachable


class PopulateCacheFlushTests(TransactionTestCase):
    """Reset endpoints run populate while other drafts are live on the same Redis."""

    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        self.r = get_redis_client()
        self.count_key = conn_count_key("teamdraft", 987654)
        self.heartbeat = heartbeat_key("teamdraft", 987654, 1)
        self.addCleanup(self.r.delete, self.count_key, self.heartbeat)

    def cacheops_keys(self) -> list[bytes]:
        prefix = settings.CACHEOPS_PREFIX(None)
        return list(cacheops_redis.scan_iter(match=f"{prefix}*", count=500))

    def test_flush_keeps_live_draft_state_and_drops_cached_queries(self) -> None:
        increment_connection_count("teamdraft", 987654, "c1")
        self.r.set(self.heartbeat, "1.0")
        tournament = Tournament.objects.create(
            name="flush probe", date_played=date.today()
        )
        list(Tournament.objects.filter(pk=tournament.pk).cache())
        self.assertTrue(self.cacheops_keys())

        flush_redis_cache()

        self.assertEqual(get_connection_count("teamdraft", 987654), 1)
        self.assertEqual(self.r.get(self.heartbeat), "1.0")
        self.assertEqual(self.cacheops_keys(), [])

    def test_a_cache_miss_racing_the_flush_never_leaves_a_result_without_its_invalidator(
        self,
    ) -> None:
        prefix = settings.CACHEOPS_PREFIX(None)
        first = Tournament.objects.create(name="flush race a", date_played=date.today())
        second = Tournament.objects.create(
            name="flush race b", date_played=date.today()
        )
        list(Tournament.objects.filter(pk=first.pk).cache())
        real_scan = cacheops_redis.scan_iter

        def scan_with_concurrent_miss(
            *args: object, **kwargs: object
        ) -> Iterator[bytes]:
            seen = list(real_scan(*args, **kwargs))
            yield from seen
            # Another process misses the cache mid-flush; SCAN then reports its conj
            # key but not its result key.
            list(Tournament.objects.filter(pk=second.pk).cache())
            yield from (
                k
                for k in real_scan(match=f"{prefix}conj:*", count=500)
                if k not in seen
            )

        with patch.object(cacheops_redis, "scan_iter", scan_with_concurrent_miss):
            flush_redis_cache()

        conj_members: set[bytes] = set()
        for conj in real_scan(match=f"{prefix}conj:*", count=500):
            conj_members |= cacheops_redis.smembers(conj)
        orphans = [
            k
            for k in real_scan(match=f"{prefix}q:*", count=500)
            if k not in conj_members
        ]
        self.assertEqual(orphans, [])
