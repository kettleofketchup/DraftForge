from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import League, Organization, Tournament
from org.models import OrgUser
from tests.populate.tournament_discovery import populate_tournament_discovery

LIST_URL = "/api/tournaments-list/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
EXPECTED_TOURNAMENTS: dict[int, tuple[str, str, int]] = {
    900: ("Discovery Home Live", "in_progress", 30),
    901: ("Discovery Home Soon", "future", 30),
    902: ("Discovery Home Later", "future", 30),
    903: ("Discovery Home Finished", "past", 30),
    904: ("Discovery Home Stale", "future", 30),
    905: ("Discovery Away Cup", "future", 31),
}


@override_settings(CACHEOPS_ENABLED=False)
class TournamentDiscoverySeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_tournament_discovery(force=True)
        populate_tournament_discovery(force=True)

    def setUp(self) -> None:
        self.client = APIClient()

    def _pks(self, query: str) -> set[int]:
        with mock.patch("app.tournament_buckets._now", return_value=NOW):
            response = self.client.get(f"{LIST_URL}{query}")
        self.assertEqual(response.status_code, 200)
        return {row["pk"] for row in response.json()}

    def test_organizations_and_leagues_exist(self) -> None:
        self.assertEqual(
            set(
                Organization.objects.filter(pk__in=[30, 31]).values_list(
                    "pk", flat=True
                )
            ),
            {30, 31},
        )
        leagues = dict(
            League.objects.filter(pk__in=[30, 31]).values_list("pk", "organization_id")
        )
        self.assertEqual(leagues, {30: 30, 31: 31})

    def test_tournaments_have_expected_names_states_and_leagues(self) -> None:
        rows = {
            pk: (name, state, league_id)
            for pk, name, state, league_id in Tournament.objects.filter(
                pk__in=EXPECTED_TOURNAMENTS
            ).values_list("pk", "name", "state", "league_id")
        }
        self.assertEqual(rows, EXPECTED_TOURNAMENTS)

    def test_member_belongs_to_home_org_only(self) -> None:
        org_ids = list(
            OrgUser.objects.filter(user__username="discovery_member").values_list(
                "organization_id", flat=True
            )
        )
        self.assertEqual(org_ids, [30])

    def test_upcoming_bucket_holds_future_and_live_rows(self) -> None:
        upcoming = self._pks("?bucket=upcoming") & set(EXPECTED_TOURNAMENTS)
        self.assertEqual(upcoming, {900, 901, 902, 905})

    def test_archived_bucket_holds_past_and_stale_rows(self) -> None:
        archived = self._pks("?bucket=archived") & set(EXPECTED_TOURNAMENTS)
        self.assertEqual(archived, {903, 904})
