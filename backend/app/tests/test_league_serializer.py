from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError

from app.models import CustomUser, League, Organization, PositionsModel
from app.serializers import LeagueSerializer


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

    def test_rejects_none(self):
        with self.assertRaises(ValidationError):
            self._validate(None, instance=self.league)

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


from rest_framework.test import APIClient


class LeaguePatchSteamLeagueIdTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(username="lp_admin", password="x")
        cls.admin.positions = PositionsModel.objects.create()
        cls.admin.save()
        cls.regular = CustomUser.objects.create_user(username="lp_regular", password="x")
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
        from cacheops import invalidate_all
        invalidate_all()

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
