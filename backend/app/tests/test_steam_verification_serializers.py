from typing import Any

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from app.serializers import TournamentUserSerializer, UserSerializer
from events.models import Event, EventSignup
from events.services import process_rsvp, staff_add_signup
from events.tests.base import EventTestCase
from league.models import LeagueUser
from league.serializers import LeagueUserSerializer
from org.mmr import game_mmrs_prefetch
from org.models import Organization, OrgUser
from org.serializers import OrgUserSerializer

COLUMN_KEYS = {
    "steam_account_verified",
    "steam_account_verified_at",
    "steam_account_exists_checked",
}
ORG_NAME_KEY = "steam_account_verified_org_name"

USER_LIST_QUERIES = 46
ORG_MEMBERS_QUERIES = 4
SIGNUP_LIST_QUERIES = 6


@override_settings(CACHEOPS_ENABLED=False)
class SteamVerificationSerializerTests(EventTestCase):
    def setUp(self) -> None:
        self.vouching_org = Organization.objects.create(
            name="Vouching Org", owner=self.admin
        )
        self.target = self.make_user()
        self._verify(self.target, 4242, self.vouching_org)

    def _verify(self, user: CustomUser, account_id: int, org: Organization) -> None:
        now = timezone.now()
        user.steam_account_id = account_id
        user.steam_account_verified_at = now
        user.steam_account_verified_org = org
        user.steam_account_exists_checked_at = now
        user.save()

    def _client(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def _signups(self, event: Event, viewer: CustomUser | None) -> list[dict[str, Any]]:
        response = self._client(viewer).get("/api/events/signups/", {"event": event.pk})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return body["results"] if isinstance(body, dict) else body

    def _row(self, rows: list[dict[str, Any]], user: CustomUser) -> dict[str, Any]:
        return next(row for row in rows if row["user"] == user.pk)

    def _assert_columns(self, data: dict[str, Any]) -> None:
        self.assertTrue(COLUMN_KEYS <= set(data))
        self.assertIs(data["steam_account_verified"], True)
        self.assertIsInstance(data["steam_account_verified_at"], str)
        self.assertIs(data["steam_account_exists_checked"], True)

    def test_tournament_user_serializer_fields(self) -> None:
        data = TournamentUserSerializer(self.target).data
        self._assert_columns(data)
        self.assertNotIn(ORG_NAME_KEY, data)

    def test_unverified_columns(self) -> None:
        user = self.make_user()
        user.steam_account_id = 5151
        user.save()
        data = TournamentUserSerializer(user).data
        self.assertIs(data["steam_account_verified"], False)
        self.assertIsNone(data["steam_account_verified_at"])
        self.assertIs(data["steam_account_exists_checked"], False)

    def test_org_user_serializer_fields(self) -> None:
        org_user = OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=True)).get(
            user=self.target, organization=self.org
        )
        plain = OrgUserSerializer(org_user).data
        self._assert_columns(plain)
        self.assertNotIn(ORG_NAME_KEY, plain)

        response = self._client(self.admin).get(
            f"/api/organizations/{self.org.pk}/users/"
        )
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json() if r["pk"] == self.target.pk)
        self._assert_columns(row)
        self.assertEqual(row[ORG_NAME_KEY], "Vouching Org")

    def test_league_user_serializer_fields(self) -> None:
        org_user = OrgUser.objects.get(user=self.target, organization=self.org)
        LeagueUser.objects.create(
            user=self.target, org_user=org_user, league=self.league, mmr=3000
        )
        league_user = (
            LeagueUser.objects.select_related("user", "org_user")
            .prefetch_related("org_user__game_mmrs")
            .get(user=self.target, league=self.league)
        )
        data = LeagueUserSerializer(league_user).data
        self._assert_columns(data)
        self.assertNotIn(ORG_NAME_KEY, data)

    def test_user_serializer_fields_read_only(self) -> None:
        self._assert_columns(UserSerializer(self.target).data)
        superuser = CustomUser.objects.create_superuser(
            username="sv_ser_super", password="x", email="sv_ser_super@example.com"
        )
        response = self._client(superuser).patch(
            f"/api/users/{self.target.pk}/",
            {
                "steam_account_verified": False,
                "steam_account_verified_at": None,
                "steam_account_exists_checked": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.steam_account_verified)
        self.assertIsNotNone(self.target.steam_account_exists_checked_at)
        self.assertNotIn("steam_account_verified_by", response.json())

    def test_dota_profile_payload_fields(self) -> None:
        response = self._client(self.admin).get(
            f"/api/organizations/{self.org.pk}/users/{self.target.pk}/dota-profile/"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_columns(data)
        self.assertEqual(data[ORG_NAME_KEY], "Vouching Org")

    def test_dota_profile_unverified_has_no_org_name(self) -> None:
        user = self.make_user()
        user.steam_account_id = 5151
        user.save()
        response = self._client(user).get(
            f"/api/organizations/{self.org.pk}/my-dota-profile/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["steam_account_verified"], False)
        self.assertIsNone(response.json()[ORG_NAME_KEY])

    def test_signup_can_verify_true_for_event_staff_self_signup(self) -> None:
        event = self.make_event()
        signup = process_rsvp(event, self.target)
        self.assertTrue(signup.self_made)
        row = self._row(self._signups(event, self.admin), self.target)
        self.assertIs(row["can_verify_steam_account"], True)
        self._assert_columns(row["user_data"])
        self.assertEqual(row["user_data"][ORG_NAME_KEY], "Vouching Org")
        self.assertNotIn("steam_account_verified_by", row["user_data"])

    def test_signup_can_verify_false_for_own_row(self) -> None:
        event = self.make_event()
        signup = process_rsvp(event, self.admin)
        self.assertTrue(signup.self_made)
        row = self._row(self._signups(event, self.admin), self.admin)
        self.assertIs(row["can_verify_steam_account"], False)

    def test_signup_can_verify_false_for_on_behalf_signup(self) -> None:
        event = self.make_event()
        signup = staff_add_signup(event, self.target)
        self.assertFalse(signup.self_made)
        row = self._row(self._signups(event, self.admin), self.target)
        self.assertIs(row["can_verify_steam_account"], False)

    def test_signup_can_verify_false_for_non_staff(self) -> None:
        event = self.make_event()
        process_rsvp(event, self.target)
        for viewer in (None, self.unrelated_user):
            row = self._row(self._signups(event, viewer), self.target)
            self.assertIs(row["can_verify_steam_account"], False)
            self.assertIsNone(row["user_data"][ORG_NAME_KEY])
            self._assert_columns(row["user_data"])
        own = self._row(self._signups(event, self.target), self.target)
        self.assertIs(own["can_verify_steam_account"], False)
        self.assertEqual(own["user_data"][ORG_NAME_KEY], "Vouching Org")

    def test_signup_tournament_event_user_data_carries_org_name(self) -> None:
        event = self.make_event(tournament_league=self.league)
        process_rsvp(event, self.target)
        row = self._row(self._signups(event, self.admin), self.target)
        self.assertEqual(row["user_data"][ORG_NAME_KEY], "Vouching Org")


@override_settings(CACHEOPS_ENABLED=False)
class SteamVerificationQueryCountTests(EventTestCase):
    """Counts measured before the verification fields existed; must not grow."""

    def setUp(self) -> None:
        self.members: list[CustomUser] = []
        for i in range(3):
            org = Organization.objects.create(name=f"QC Org {i}", owner=self.admin)
            user = self.make_user()
            now = timezone.now()
            user.steam_account_id = 7000 + i
            user.steam_account_verified_at = now
            user.steam_account_verified_org = org
            user.steam_account_exists_checked_at = now
            user.save()
            self.members.append(user)

    def test_user_list_query_count(self) -> None:
        client = APIClient()
        with self.assertNumQueries(USER_LIST_QUERIES):
            response = client.get("/api/users/")
        self.assertEqual(response.status_code, 200)

    def test_org_members_query_count(self) -> None:
        client = APIClient()
        client.force_authenticate(self.admin)
        with self.assertNumQueries(ORG_MEMBERS_QUERIES):
            response = client.get(f"/api/organizations/{self.org.pk}/users/")
        self.assertEqual(response.status_code, 200)

    def test_signup_list_query_count(self) -> None:
        event = self.make_event()
        for user in self.members:
            self.assertTrue(process_rsvp(event, user).self_made)
        self.assertEqual(EventSignup.objects.filter(event=event).count(), 3)
        client = APIClient()
        client.force_authenticate(self.admin)
        with self.assertNumQueries(SIGNUP_LIST_QUERIES):
            response = client.get("/api/events/signups/", {"event": event.pk})
        self.assertEqual(response.status_code, 200)
