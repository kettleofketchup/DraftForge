from django.test import TestCase
from rest_framework.exceptions import ValidationError

from app.models import League, Organization
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
