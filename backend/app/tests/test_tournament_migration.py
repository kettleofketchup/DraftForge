from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    DraftStyles,
    GameType,
    League,
    Organization,
    PositionsModel,
    Tournament,
)


class TournamentNewFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.positions = PositionsModel.objects.create()
        cls.user = CustomUser.objects.create_user(
            username="tmigrate", password="testpass"
        )
        cls.user.positions = cls.positions
        cls.user.save()
        cls.org = Organization.objects.create(name="TMigrate Org", owner=cls.user)
        cls.league = League.objects.create(
            name="TMigrate League",
            organization=cls.org,
            steam_league_id=99995,
        )
        cls.now = timezone.now()

    def test_tournament_game_type(self):
        t = Tournament.objects.create(
            name="Test",
            league=self.league,
            date_played=self.now,
            game_type=GameType.DOTA2,
        )
        self.assertEqual(t.game_type, GameType.DOTA2)

    def test_tournament_draft_type(self):
        t = Tournament.objects.create(
            name="Test",
            league=self.league,
            date_played=self.now,
            draft_type=DraftStyles.shuffle.value,
        )
        self.assertEqual(t.draft_type, "shuffle")

    def test_tournament_people_per_team(self):
        t = Tournament.objects.create(
            name="Test",
            league=self.league,
            date_played=self.now,
            people_per_team=6,
        )
        self.assertEqual(t.people_per_team, 6)

    def test_tournament_defaults(self):
        t = Tournament.objects.create(
            name="Test",
            league=self.league,
            date_played=self.now,
        )
        self.assertEqual(t.game_type, 1)
        self.assertEqual(t.draft_type, "shuffle")
        self.assertEqual(t.people_per_team, 5)
        self.assertIsNone(t.number_of_teams)
