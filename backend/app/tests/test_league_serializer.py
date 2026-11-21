from django.db import connection, reset_queries
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from app.models import CustomUser, League, PositionsModel
from app.serializers import LeagueSerializer
from league.models import LeagueUser
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache


class ValidateSteamLeagueIdTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Test Org")
        cls.league = League.objects.create(
            organization=cls.org,
            name="Existing League",
            steam_league_id=10001,
        )
        cls.other_league = League.objects.create(
            organization=cls.org,
            name="Other League",
            steam_league_id=10002,
        )

    def _validate(self, value, instance=None):
        serializer = LeagueSerializer(instance=instance)
        return serializer.validate_steam_league_id(value)

    def test_rejects_zero(self):
        with self.assertRaises(ValidationError):
            self._validate(0, instance=self.league)

    def test_rejects_negative(self):
        with self.assertRaises(ValidationError):
            self._validate(-1, instance=self.league)

    def test_accepts_none(self):
        # steam_league_id is optional — leagues without a Steam ID are valid.
        result = self._validate(None, instance=self.league)
        self.assertIsNone(result)

    def test_rejects_collision_with_another_league(self):
        with self.assertRaises(ValidationError) as ctx:
            self._validate(self.other_league.steam_league_id, instance=self.league)
        self.assertIn("Other League", str(ctx.exception))
        self.assertIn("already in use", str(ctx.exception))

    def test_accepts_unchanged_value_on_self(self):
        result = self._validate(self.league.steam_league_id, instance=self.league)
        self.assertEqual(result, self.league.steam_league_id)

    def test_accepts_fresh_unused_id(self):
        result = self._validate(99999, instance=self.league)
        self.assertEqual(result, 99999)

    def test_accepts_unused_id_on_create_no_instance(self):
        result = self._validate(99998, instance=None)
        self.assertEqual(result, 99998)

    def test_rejects_collision_on_create_no_instance(self):
        with self.assertRaises(ValidationError):
            self._validate(self.league.steam_league_id, instance=None)


class LeaguePatchSteamLeagueIdTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(username="lp_admin", password="x")
        cls.admin.positions = PositionsModel.objects.create()
        cls.admin.save()
        cls.regular = CustomUser.objects.create_user(
            username="lp_regular", password="x"
        )
        cls.regular.positions = PositionsModel.objects.create()
        cls.regular.save()
        cls.org = Organization.objects.create(name="LP Org", owner=cls.admin)
        cls.league = League.objects.create(
            organization=cls.org,
            name="LP League",
            steam_league_id=30001,
        )
        cls.league.admins.add(cls.admin)

    def setUp(self):
        self.client = APIClient()

    def test_admin_can_update_steam_league_id(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"steam_league_id": 30009},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.league.refresh_from_db()
        self.assertEqual(self.league.steam_league_id, 30009)

    def test_admin_can_patch_with_unchanged_id(self):
        """No-op edit: PATCHing the same value succeeds without collision."""
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"steam_league_id": self.league.steam_league_id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_non_admin_returns_403(self):
        self.client.force_authenticate(self.regular)
        resp = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"steam_league_id": 30009},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_collision_returns_custom_validator_message(self):
        """Custom validator must not be shadowed by DRF UniqueValidator."""
        # Create a second league with a known steam_league_id
        League.objects.create(
            organization=self.org,
            name="Conflicting League",
            steam_league_id=30100,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"steam_league_id": 30100},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("steam_league_id", body)
        self.assertIn(
            "already in use by 'Conflicting League'", str(body["steam_league_id"])
        )


class LeaguePatchSteamLeagueIdCacheTest(TransactionTestCase):
    """Cache round-trip regression for League.

    `LeagueView` has no `perform_update` override — relies on cacheops
    auto-invalidation via `League.save() → invalidate_obj`. This test
    confirms a PATCH-then-GET round-trip returns the new value, not stale.
    Uses TransactionTestCase so on_commit hooks fire (mirrors the events-side
    cache test pattern).
    """

    def setUp(self):
        # Flush cacheops Redis cache to avoid stale entries from prior tests.
        flush_run_cache()

        self.admin = CustomUser.objects.create_user(username="lpc_admin", password="x")
        self.admin.positions = PositionsModel.objects.create()
        self.admin.save()
        self.org = Organization.objects.create(name="LPC Org", owner=self.admin)
        self.league = League.objects.create(
            organization=self.org,
            name="LPC League",
            steam_league_id=42001,
        )
        self.league.admins.add(self.admin)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_get_after_patch_returns_new_steam_league_id(self):
        # Prime the cache
        prime = self.client.get(f"/api/leagues/{self.league.pk}/")
        self.assertEqual(prime.status_code, 200)
        # Mutate
        patch_resp = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"steam_league_id": 42009},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        # Read through cache — must reflect the new value
        get_resp = self.client.get(f"/api/leagues/{self.league.pk}/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["steam_league_id"], 42009)


class LeagueUsersNameFieldsTest(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.staff = CustomUser.objects.create_user(
            username="lun_staff", password="x", is_staff=True
        )
        self.org = Organization.objects.create(name="LUN Org", owner=self.staff)
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _league(self, name: str, steam_id: int, size: int) -> League:
        league = League.objects.create(
            organization=self.org, name=name, steam_league_id=steam_id
        )
        for i in range(size):
            user = CustomUser.objects.create_user(
                username=f"{name}_u{i}", password="x", discordNickname=f"Global{i}"
            )
            org_user, _ = OrgUser.objects.get_or_create(
                user=user, organization=self.org
            )
            org_user.guild_nickname = f"Server{i}"
            org_user.save()
            LeagueUser.objects.get_or_create(
                user=user, org_user=org_user, league=league
            )
        return league

    def _get(self, league: League) -> tuple[list[dict], int]:
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(f"/api/leagues/{league.pk}/users/")
        self.assertEqual(response.status_code, 200)
        return response.json(), len(ctx.captured_queries)

    def test_rows_carry_server_and_global_names(self) -> None:
        rows, _ = self._get(self._league("lun_a", 51001, 1))
        self.assertEqual(rows[0]["guildNickname"], "Server0")
        self.assertEqual(rows[0]["discordNickname"], "Global0")

    def test_query_count_does_not_grow_with_rows(self) -> None:
        _, one = self._get(self._league("lun_one", 51002, 1))
        _, five = self._get(self._league("lun_five", 51003, 5))
        self.assertEqual(one, five)
