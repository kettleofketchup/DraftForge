"""Game team-change signal hooks never fail a committed Game save."""

from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftState,
    Team,
    Tournament,
)


class GameTeamChangeHookTests(TransactionTestCase):
    def setUp(self) -> None:
        tournament = Tournament.objects.create(
            name="Hook Tournament", date_played=timezone.now()
        )
        teams = []
        for name in ("Radiant", "Dire", "Dire2"):
            captain = CustomUser.objects.create(
                username=f"hook_{name}", discordId=f"hook_{name}"
            )
            teams.append(
                Team.objects.create(tournament=tournament, name=name, captain=captain)
            )
        self.radiant, self.dire, self.dire2 = teams
        self.game = Game.objects.create(
            tournament=tournament, radiant_team=self.radiant, dire_team=self.dire
        )
        self.draft = HeroDraft.objects.create(
            game=self.game, state=HeroDraftState.DRAFTING
        )
        DraftTeam.objects.create(draft=self.draft, tournament_team=self.radiant)
        self.dt_dire = DraftTeam.objects.create(
            draft=self.draft, tournament_team=self.dire
        )

    def failing_broadcast(self) -> object:
        return patch(
            "app.signals._broadcast_draft_event", side_effect=RuntimeError("down")
        )

    def test_reset_saves_when_the_broadcast_hook_raises(self) -> None:
        with self.failing_broadcast() as broadcast_mock:
            self.game.dire_team = self.dire2
            self.game.save()
        broadcast_mock.assert_called_once()
        self.dt_dire.refresh_from_db()
        self.assertEqual(self.dt_dire.tournament_team, self.dire2)
        self.assertEqual(
            HeroDraft.objects.nocache().get(pk=self.draft.pk).state,
            HeroDraftState.WAITING_FOR_CAPTAINS,
        )

    def test_clear_saves_when_the_broadcast_hook_raises(self) -> None:
        with self.failing_broadcast() as broadcast_mock:
            self.game.dire_team = None
            self.game.save()
        broadcast_mock.assert_called_once()
        self.assertFalse(HeroDraft.objects.filter(pk=self.draft.pk).exists())
        self.assertIsNone(Game.objects.nocache().get(pk=self.game.pk).dire_team_id)
