from datetime import date

from django.test import TestCase

from app.functions.herodraft import CAPTAINS_MODE_SEQUENCE, build_draft_rounds
from app.models import CustomUser, DraftTeam, Game, HeroDraft, Team, Tournament


class BuildDraftRoundsTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(
            username="captain1", password="test"
        )
        self.user2 = CustomUser.objects.create_user(
            username="captain2", password="test"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )
        self.team1 = Team.objects.create(
            name="Team 1", tournament=self.tournament, captain=self.user1
        )
        self.team2 = Team.objects.create(
            name="Team 2", tournament=self.tournament, captain=self.user2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def test_builds_24_rounds(self):
        """build_draft_rounds creates exactly 24 rounds."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        self.assertEqual(draft.rounds.count(), 24)

    def test_correct_sequence(self):
        """Rounds follow the updated Captain's Mode sequence."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        rounds = list(draft.rounds.all())

        # Verify first ban phase: F-F-S-S-F-S-S
        self.assertEqual(rounds[0].draft_team, first_team)
        self.assertEqual(rounds[0].action_type, "ban")
        self.assertEqual(rounds[1].draft_team, first_team)
        self.assertEqual(rounds[1].action_type, "ban")
        self.assertEqual(rounds[2].draft_team, second_team)
        self.assertEqual(rounds[3].draft_team, second_team)
        self.assertEqual(rounds[4].draft_team, first_team)
        self.assertEqual(rounds[5].draft_team, second_team)
        self.assertEqual(rounds[6].draft_team, second_team)

        # Verify first pick phase: F-S (rounds 8-9)
        self.assertEqual(rounds[7].action_type, "pick")
        self.assertEqual(rounds[7].draft_team, first_team)
        self.assertEqual(rounds[8].action_type, "pick")
        self.assertEqual(rounds[8].draft_team, second_team)

    def test_ban_and_pick_counts(self):
        """First team has 6 bans, 5 picks. Second team has 8 bans, 5 picks."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        first_bans = draft.rounds.filter(
            draft_team=first_team, action_type="ban"
        ).count()
        first_picks = draft.rounds.filter(
            draft_team=first_team, action_type="pick"
        ).count()
        second_bans = draft.rounds.filter(
            draft_team=second_team, action_type="ban"
        ).count()
        second_picks = draft.rounds.filter(
            draft_team=second_team, action_type="pick"
        ).count()

        self.assertEqual(first_bans, 6)
        self.assertEqual(first_picks, 5)
        self.assertEqual(second_bans, 8)
        self.assertEqual(second_picks, 5)
