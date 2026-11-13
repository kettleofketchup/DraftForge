"""`organizations` and `open_signups` scope filters on GET /api/tournaments-list/."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import League, Organization, Tournament
from events.constants import EventState
from events.models import Event

LIST_URL = "/api/tournaments-list/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@override_settings(CACHEOPS_ENABLED=False)
class TournamentListScopeTests(TestCase):
    rows: dict[str, Tournament]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.home = Organization.objects.create(name="Home Org")
        cls.side = Organization.objects.create(name="Side Org")
        cls.away = Organization.objects.create(name="Away Org")
        leagues = {
            org.pk: League.objects.create(organization=org, name=f"{org.name} League")
            for org in (cls.home, cls.side, cls.away)
        }

        def make(name: str, org: Organization, state: str, days: int) -> Tournament:
            return Tournament.objects.create(
                name=name,
                state=state,
                date_played=NOW + timedelta(days=days),
                league=leagues[org.pk],
            )

        cls.rows = {
            "home_future": make("Home Future", cls.home, "future", 3),
            "home_past": make("Home Past", cls.home, "past", -30),
            "side_future": make("Side Future", cls.side, "future", 4),
            "away_open": make("Away Open", cls.away, "future", 5),
            "away_closed": make("Away Closed", cls.away, "future", 6),
            "away_past_open": make("Away Past Open", cls.away, "past", -30),
        }
        for key, state in (
            ("away_open", EventState.SIGNUPS_OPEN),
            ("away_closed", EventState.UPCOMING),
            ("away_past_open", EventState.SIGNUPS_OPEN),
        ):
            Event.objects.create(
                organization=cls.away,
                name=f"{key} event",
                scheduled_at=cls.rows[key].date_played,
                state=state,
                tournament=cls.rows[key],
            )

    def setUp(self) -> None:
        self.client = APIClient()

    def get(self, qs: str = "") -> Response:
        with mock.patch("app.tournament_buckets._now", return_value=NOW):
            return self.client.get(f"{LIST_URL}{qs}")

    def rows_for(self, qs: str) -> list[dict[str, Any]]:
        response = self.get(qs)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        return data["results"] if isinstance(data, dict) else data

    def pk_set(self, *keys: str) -> set[int]:
        return {self.rows[key].pk for key in keys}

    def pks(self, qs: str) -> set[int]:
        return {row["pk"] for row in self.rows_for(qs)}

    def test_organizations_filters_to_listed_orgs(self) -> None:
        qs = f"?bucket=upcoming&organizations={self.home.pk},{self.side.pk}"
        self.assertEqual(self.pks(qs), self.pk_set("home_future", "side_future"))

    def test_organizations_ignores_order_spacing_and_duplicates(self) -> None:
        qs = f"?bucket=upcoming&organizations={self.side.pk}, {self.home.pk},{self.side.pk}"
        self.assertEqual(self.pks(qs), self.pk_set("home_future", "side_future"))

    def test_empty_organizations_matches_nothing(self) -> None:
        self.assertEqual(self.pks("?bucket=upcoming&organizations="), set())

    def test_open_signups_alone_returns_open_signup_tournaments(self) -> None:
        self.assertEqual(
            self.pks("?bucket=upcoming&open_signups=1"), self.pk_set("away_open")
        )

    def test_organizations_plus_open_signups_is_a_union(self) -> None:
        qs = f"?bucket=upcoming&organizations={self.home.pk}&open_signups=1"
        self.assertEqual(self.pks(qs), self.pk_set("home_future", "away_open"))

    def test_empty_organizations_plus_open_signups(self) -> None:
        qs = "?bucket=upcoming&organizations=&open_signups=1"
        self.assertEqual(self.pks(qs), self.pk_set("away_open"))

    def test_open_signups_zero_is_ignored(self) -> None:
        qs = f"?bucket=upcoming&organizations={self.home.pk}&open_signups=0"
        self.assertEqual(self.pks(qs), self.pk_set("home_future"))

    def test_archived_member_orgs(self) -> None:
        qs = f"?bucket=archived&organizations={self.home.pk}"
        self.assertEqual(self.pks(qs), self.pk_set("home_past"))

    def test_league_and_search_narrow_the_scope(self) -> None:
        qs = f"?bucket=upcoming&organizations={self.home.pk}&open_signups=1&search=away"
        self.assertEqual(self.pks(qs), self.pk_set("away_open"))
        league = self.rows["home_future"].league_id
        qs = f"?bucket=upcoming&organizations={self.home.pk}&open_signups=1&league={league}"
        self.assertEqual(self.pks(qs), self.pk_set("home_future"))

    def test_rows_carry_signups_open(self) -> None:
        flags = {row["pk"]: row["signups_open"] for row in self.rows_for("")}
        self.assertEqual(
            {pk for pk, is_open in flags.items() if is_open},
            self.pk_set("away_open", "away_past_open"),
        )
        self.assertEqual(len(flags), len(self.rows))

    def test_paginated_scope(self) -> None:
        qs = f"?bucket=archived&organizations={self.home.pk}&page=1"
        data = self.get(qs).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["pk"], self.rows["home_past"].pk)

    def test_invalid_scope_params_400(self) -> None:
        cases = [
            ("organizations=abc", "organizations"),
            ("organizations=1,x", "organizations"),
            ("organizations=0", "organizations"),
            ("organizations=-3", "organizations"),
            ("organizations=1,,2", "organizations"),
            ("organizations=" + ",".join(str(i) for i in range(1, 102)), "organizations"),
            ("open_signups=yes", "open_signups"),
            ("open_signups=", "open_signups"),
            (f"organization={1}&organizations=2", "organizations"),
        ]
        for qs, field in cases:
            with self.subTest(qs=qs):
                response = self.get(f"?{qs}")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json())

    def test_open_signups_ignores_deadline_and_open_time(self) -> None:
        event = Event.objects.get(tournament=self.rows["away_open"])
        event.signup_deadline_hours = 1
        event.signups_open_at = NOW + timedelta(hours=1)
        event.allow_user_signups = False
        event.save()
        later = event.scheduled_at - timedelta(minutes=30)
        with mock.patch("app.tournament_buckets._now", return_value=later):
            response = self.client.get(f"{LIST_URL}?bucket=upcoming&open_signups=1")
        self.assertEqual(
            {row["pk"] for row in response.json()}, self.pk_set("away_open")
        )
