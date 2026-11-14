from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import League, Organization, Tournament
from app.tournament_buckets import tournament_bucket_cutoff

LIST_URL = "/api/tournaments-list/"
PLAYED = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


@override_settings(CACHEOPS_ENABLED=False)
class LeagueMinimalSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(
            name="Logo Org", logo="https://cdn.example/l.png"
        )
        cls.blank_org = Organization.objects.create(name="Blank Logo Org", logo="")
        cls.league = League.objects.create(organization=cls.org, name="Logo League")
        cls.blank_league = League.objects.create(
            organization=cls.blank_org, name="Blank Logo League"
        )
        cls.orphan_league = League.objects.create(
            organization=None, name="Orphan League"
        )

    def setUp(self) -> None:
        self.client = APIClient()

    def _row(self, tournament: Tournament) -> dict[str, Any]:
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        return next(r for r in response.json() if r["pk"] == tournament.pk)

    def _tournament(self, league: League | None, name: str = "T") -> Tournament:
        return Tournament.objects.create(name=name, date_played=PLAYED, league=league)

    def test_row_league_carries_organization_id_and_logo(self) -> None:
        row = self._row(self._tournament(self.league))
        expected = {
            "pk": self.league.pk,
            "name": "Logo League",
            "organization_name": "Logo Org",
            "organization_id": self.org.pk,
            "organization_logo": "https://cdn.example/l.png",
        }
        self.assertEqual({k: row["league"][k] for k in expected}, expected)

    def test_blank_logo_is_null(self) -> None:
        row = self._row(self._tournament(self.blank_league))
        self.assertEqual(row["league"]["organization_id"], self.blank_org.pk)
        self.assertIsNone(row["league"]["organization_logo"])

    def test_league_without_organization_has_null_org_fields(self) -> None:
        row = self._row(self._tournament(self.orphan_league))
        self.assertIsNone(row["league"]["organization_id"])
        self.assertIsNone(row["league"]["organization_name"])
        self.assertIsNone(row["league"]["organization_logo"])

    def test_tournament_without_league_has_null_league(self) -> None:
        row = self._row(self._tournament(None))
        self.assertIsNone(row["league"])

    def _count_list_queries(self) -> int:
        # CaptureQueriesContext drops queries when the request resets the log.
        seen: list[str] = []

        def record(
            execute: Callable[..., Any],
            sql: str,
            params: Any,
            many: bool,
            context: dict[str, Any],
        ) -> Any:
            seen.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(record):
            response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        return len(seen)

    def test_query_count_constant_in_row_count(self) -> None:
        leagues = [self.league, self.blank_league]
        for i in range(2):
            self._tournament(leagues[i % 2], name=f"T{i}")
        two_rows = self._count_list_queries()
        orgs = [
            Organization.objects.create(
                name=f"Extra Org {i}", logo=f"https://cdn.example/{i}.png"
            )
            for i in range(4)
        ]
        for i, org in enumerate(orgs):
            league = League.objects.create(organization=org, name=f"Extra League {i}")
            self._tournament(league, name=f"X{i}")
        self.assertEqual(Tournament.objects.count(), 6)
        self.assertEqual(self._count_list_queries(), two_rows)


NOW = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 11, 11, tzinfo=UTC)


class _BucketFixtureMixin(TestCase):
    rows: dict[str, Tournament]

    @classmethod
    def setUpTestData(cls) -> None:
        alpha_org = Organization.objects.create(name="Alpha Org")
        beta_org = Organization.objects.create(name="Beta Org")
        alpha_league = League.objects.create(organization=alpha_org, name="Alpha League")
        beta_league = League.objects.create(organization=beta_org, name="Beta League")
        specs: list[tuple[str, str, datetime, League | None]] = [
            ("future_ahead", "future", NOW + timedelta(days=5), alpha_league),
            ("live_today", "in_progress", NOW - timedelta(hours=1), alpha_league),
            ("stale_minus_1s", "future", CUTOFF - timedelta(seconds=1), beta_league),
            ("at_cutoff", "future", CUTOFF, beta_league),
            ("past_ahead", "past", NOW + timedelta(days=3), alpha_league),
            ("invalid_state", "future", NOW + timedelta(days=2), beta_league),
            ("grace_yesterday", "future", NOW - timedelta(days=1), beta_league),
            ("tomorrow", "future", NOW + timedelta(days=1), alpha_league),
            ("no_league", "future", NOW + timedelta(days=7), None),
        ]
        cls.rows = {
            key: Tournament.objects.create(
                name=f"{key} Cup", state=state, date_played=played, league=league
            )
            for key, state, played, league in specs
        }
        Tournament.objects.filter(pk=cls.rows["invalid_state"].pk).update(
            state="ongoing"
        )
        cls.alpha_keys = {"future_ahead", "live_today", "past_ahead", "tomorrow"}

    def setUp(self) -> None:
        self.client = APIClient()

    def get(self, qs: str = "") -> Response:
        with mock.patch("app.tournament_buckets._now", return_value=NOW):
            return self.client.get(f"{LIST_URL}{qs}")

    def pks(self, qs: str) -> list[int]:
        response = self.get(qs)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) else data
        return [row["pk"] for row in rows]

    def pk_set(self, *keys: str) -> set[int]:
        return {self.rows[key].pk for key in keys}


UPCOMING_KEYS = (
    "future_ahead",
    "live_today",
    "at_cutoff",
    "grace_yesterday",
    "tomorrow",
    "no_league",
)
ARCHIVED_KEYS = ("stale_minus_1s", "past_ahead", "invalid_state")


@override_settings(CACHEOPS_ENABLED=False)
class TournamentListBucketTests(_BucketFixtureMixin):
    def test_upcoming_membership(self) -> None:
        self.assertEqual(set(self.pks("?bucket=upcoming")), self.pk_set(*UPCOMING_KEYS))

    def test_archived_membership(self) -> None:
        self.assertEqual(set(self.pks("?bucket=archived")), self.pk_set(*ARCHIVED_KEYS))

    def test_buckets_partition_all_rows(self) -> None:
        upcoming = set(self.pks("?bucket=upcoming"))
        archived = set(self.pks("?bucket=archived"))
        self.assertEqual(upcoming | archived, {t.pk for t in self.rows.values()})
        self.assertEqual(upcoming & archived, set())

    def test_upcoming_order(self) -> None:
        expected = [
            self.rows[key].pk
            for key in (
                "live_today",
                "tomorrow",
                "future_ahead",
                "no_league",
                "at_cutoff",
                "grace_yesterday",
            )
        ]
        self.assertEqual(self.pks("?bucket=upcoming"), expected)

    def test_upcoming_order_breaks_date_ties_by_pk(self) -> None:
        played = NOW + timedelta(days=10)
        first = Tournament.objects.create(name="Tie One", date_played=played)
        second = Tournament.objects.create(name="Tie Two", date_played=played)
        pks = self.pks("?bucket=upcoming")
        self.assertLess(pks.index(first.pk), pks.index(second.pk))
        self.assertEqual(pks.index(second.pk), pks.index(first.pk) + 1)

    def test_archived_order(self) -> None:
        pks = self.pks("?bucket=archived")
        dates = [Tournament.objects.get(pk=pk).date_played for pk in pks]
        self.assertEqual(len(dates), 3)
        self.assertTrue(all(a > b for a, b in zip(dates, dates[1:])), dates)

    def test_invalid_params_400(self) -> None:
        cases = [
            ("bucket=bogus", "bucket"),
            ("organization=abc", "organization"),
            ("league=x", "league"),
            ("bucket=archived&page=x", "page"),
            ("bucket=archived&page_size=x", "page_size"),
            ("bucket=archived&page=0", "page"),
            ("bucket=archived&page_size=0", "page_size"),
            ("bucket=archived&page_size=-5", "page_size"),
            ("page=1", "page"),
        ]
        for qs, field in cases:
            with self.subTest(qs=qs):
                response = self.get(f"?{qs}")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json())
        self.assertEqual(
            self.get("?bucket=bogus").json(),
            {"bucket": ["Must be 'upcoming' or 'archived'."]},
        )

    def test_organization_zero_is_empty(self) -> None:
        response = self.get("?organization=0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_retrieve_ok(self) -> None:
        pk = self.rows["future_ahead"].pk
        response = self.get(f"{pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pk"], pk)

    def test_cutoff_computed_once(self) -> None:
        with mock.patch(
            "app.views_main.tournament_bucket_cutoff", wraps=tournament_bucket_cutoff
        ) as spy:
            for qs in ("", "?bucket=upcoming", "?bucket=archived&page=1"):
                with self.subTest(qs=qs):
                    spy.reset_mock()
                    self.assertEqual(self.get(qs).status_code, 200)
                    self.assertEqual(spy.call_count, 1)

    def test_search_name_org_league_case_insensitive(self) -> None:
        alpha_upcoming = self.pk_set(*(set(UPCOMING_KEYS) & self.alpha_keys))
        self.assertEqual(set(self.pks("?bucket=upcoming&search=ALPHA ORG")), alpha_upcoming)
        self.assertEqual(
            set(self.pks("?bucket=upcoming&search=alpha league")), alpha_upcoming
        )
        self.assertEqual(
            set(self.pks("?search=FUTURE_AHEAD")), self.pk_set("future_ahead")
        )
        self.assertEqual(
            set(self.pks("?bucket=upcoming&search=a")), self.pk_set(*UPCOMING_KEYS)
        )

    def test_legacy_bare_list_contract(self) -> None:
        response = self.get()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(
            [row["pk"] for row in data],
            list(Tournament.objects.order_by("-date_played").values_list("pk", flat=True)),
        )


@override_settings(CACHEOPS_ENABLED=False)
class TournamentListPaginationTests(_BucketFixtureMixin):
    def test_paginated_envelope(self) -> None:
        response = self.get("?bucket=archived&page=1&page_size=2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"count", "next", "previous", "results"})
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNone(data["previous"])
        self.assertIn("page=2", data["next"])

        second = self.get("?bucket=archived&page=2&page_size=2").json()
        self.assertIsNone(second["next"])
        self.assertEqual(len(second["results"]), 1)

        self.assertEqual(self.get("?bucket=archived&page=9").status_code, 404)

    def test_page_size_capped(self) -> None:
        Tournament.objects.bulk_create(
            Tournament(
                name=f"Old {i}",
                state="past",
                date_played=CUTOFF - timedelta(days=i + 1),
            )
            for i in range(105)
        )
        data = self.get("?bucket=archived&page=1&page_size=500").json()
        self.assertEqual(len(data["results"]), 100)
