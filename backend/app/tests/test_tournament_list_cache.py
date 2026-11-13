"""Live-Redis cache behaviour of GET /api/tournaments-list/.

Must not run concurrently with a test stack that shares the same Redis.
"""

import pickle
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

from cacheops import invalidate_model
from cacheops.getset import cache_thing
from django.test import TransactionTestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import League, Organization, Tournament
from user.tests.test_cacheops_integration import _redis_reachable

LIST_URL = "/api/tournaments-list/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class TournamentListCacheTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        prefix = mock.patch(
            "app.tournament_list.TOURNAMENTS_LIST_CACHE_PREFIX",
            "test_tournaments_list_cache",
        )
        prefix.start()
        self.addCleanup(prefix.stop)
        for model in (Tournament, League, Organization):
            invalidate_model(model)
        self.client = APIClient()

    def _get(self, qs: str, now: datetime = NOW, **extra: Any) -> Response:
        with mock.patch("app.tournament_buckets._now", return_value=now):
            return self.client.get(f"{LIST_URL}{qs}", **extra)

    def _stored_pages(self, spy: mock.MagicMock) -> list[dict[str, Any]]:
        return [
            c.args[2]
            for c in spy.call_args_list
            if isinstance(c.args[2], dict) and {"count", "results"} <= c.args[2].keys()
        ]

    def test_org_rename_invalidates(self) -> None:
        org = Organization.objects.create(name="Original", logo="https://cdn.example/old.png")
        league = League.objects.create(organization=org, name="Cache League")
        tournament = Tournament.objects.create(
            name="Cache Cup", date_played=NOW + timedelta(days=2), league=league
        )

        def league_row() -> dict[str, Any]:
            response = self._get("?bucket=upcoming")
            self.assertEqual(response.status_code, 200)
            row = next(r for r in response.json() if r["pk"] == tournament.pk)
            return row["league"]

        self.assertEqual(league_row()["organization_name"], "Original")

        org.name = "Renamed"
        org.save()
        self.assertEqual(league_row()["organization_name"], "Renamed")

        org.logo = "https://cdn.example/new.png"
        org.save()
        self.assertEqual(league_row()["organization_logo"], "https://cdn.example/new.png")

    @override_settings(ALLOWED_HOSTS=["a.example", "b.example", "testserver"])
    def test_cached_page_is_host_free(self) -> None:
        org = Organization.objects.create(name="Archive Org", logo="")
        league = League.objects.create(organization=org, name="Archive League")
        Tournament.objects.bulk_create(
            Tournament(
                name=f"Archive {i}",
                state="past",
                date_played=NOW - timedelta(days=10 + i),
                league=league,
            )
            for i in range(30)
        )

        with mock.patch("cacheops.query.cache_thing", wraps=cache_thing) as spy:
            first = self._get("?bucket=archived&page=1", HTTP_HOST="a.example")
        self.assertEqual(first.status_code, 200)
        stored = self._stored_pages(spy)
        self.assertEqual(len(stored), 1)
        raw = pickle.dumps(stored[0])
        self.assertNotIn(b"a.example", raw)
        self.assertNotIn(b"http", raw)

        with mock.patch("cacheops.query.cache_thing", wraps=cache_thing) as spy:
            second = self._get("?bucket=archived&page=1", HTTP_HOST="b.example")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self._stored_pages(spy), [])
        self.assertEqual(second.json()["count"], 30)
        self.assertIn("b.example", second.json()["next"])

    def test_cutoff_rollover(self) -> None:
        tournament = Tournament.objects.create(
            name="Rollover Cup", date_played=datetime(2026, 11, 11, tzinfo=UTC)
        )

        def pks(qs: str, now: datetime) -> set[int]:
            response = self._get(qs, now=now)
            self.assertEqual(response.status_code, 200)
            return {row["pk"] for row in response.json()}

        self.assertIn(tournament.pk, pks("?bucket=upcoming", NOW))
        next_day = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
        self.assertNotIn(tournament.pk, pks("?bucket=upcoming", next_day))
        self.assertIn(tournament.pk, pks("?bucket=archived", next_day))
