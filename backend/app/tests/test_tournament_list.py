from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import League, Organization, Tournament

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
