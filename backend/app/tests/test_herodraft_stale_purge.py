"""Tests for the pre_save signal that purges stale HeroDraft on Game team
change (issue #235).

Scenario the signal exists to prevent: an admin sets a bracket match's
teams incorrectly, a HeroDraft is created for that match, then the bracket
is reset/re-saved with the correct teams. Without the signal, the
DraftTeam rows still FK the previous teams and the draft UI keeps showing
the wrong captains — no client reload recovers it.
"""

from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    PositionsModel,
    Team,
    Tournament,
)


def _make_user(username):
    positions = PositionsModel.objects.create()
    return CustomUser.objects.create(
        username=username,
        discordId=f"discord_{username}",
        positions=positions,
    )


def _make_team(tournament, name, captain):
    team = Team.objects.create(tournament=tournament, name=name)
    team.members.set([captain])
    team.captain = captain
    team.save()
    return team


class HeroDraftPurgedOnGameTeamChangeTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Bug 235 Tournament",
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )

        # Captains.
        self.cap_radiant_original = _make_user("light")
        self.cap_dire_original = _make_user("heff")
        self.cap_dire_corrected = _make_user("noks")

        # Tournament teams (HeroDraft FKs these via DraftTeam.tournament_team).
        self.team_radiant = _make_team(
            self.tournament, "Radiant", self.cap_radiant_original
        )
        self.team_dire_original = _make_team(
            self.tournament, "Dire (wrong)", self.cap_dire_original
        )
        self.team_dire_corrected = _make_team(
            self.tournament, "Dire (corrected)", self.cap_dire_corrected
        )

        self.tournament.users.add(
            self.cap_radiant_original,
            self.cap_dire_original,
            self.cap_dire_corrected,
        )

        # Bracket match with the wrong dire team, then a HeroDraft on it.
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_radiant,
            dire_team=self.team_dire_original,
        )
        self.draft = HeroDraft.objects.create(game=self.game)
        DraftTeam.objects.create(
            draft=self.draft, tournament_team=self.team_radiant
        )
        DraftTeam.objects.create(
            draft=self.draft, tournament_team=self.team_dire_original
        )

    def test_changing_dire_team_purges_herodraft(self):
        """The exact reproduction from issue #235: bracket is re-saved with a
        different dire team; the existing HeroDraft (stuck on the old team)
        must be deleted so the next start-draft call rebuilds a clean one."""
        draft_pk = self.draft.pk
        self.assertTrue(HeroDraft.objects.filter(pk=draft_pk).exists())

        # Simulate save_bracket overwriting the dire team on the existing Game.
        self.game.dire_team = self.team_dire_corrected
        self.game.save()

        self.assertFalse(HeroDraft.objects.filter(pk=draft_pk).exists())
        self.assertFalse(
            DraftTeam.objects.filter(draft_id=draft_pk).exists(),
            "DraftTeam rows should cascade-delete with HeroDraft",
        )

    def test_changing_radiant_team_purges_herodraft(self):
        """Same purge fires when the radiant slot is the one rewritten
        (e.g. advance_winner from an upstream game flips which team feeds
        the radiant slot of this downstream match)."""
        draft_pk = self.draft.pk
        other_radiant = _make_team(
            self.tournament, "Other Radiant", _make_user("other_cap")
        )

        self.game.radiant_team = other_radiant
        self.game.save()

        self.assertFalse(HeroDraft.objects.filter(pk=draft_pk).exists())

    def test_clearing_a_team_to_none_purges_herodraft(self):
        """The ``advance_winner`` unset path can leave a Game's slot empty;
        the captured DraftTeam.tournament_team is then orphaned. Treat the
        clear as a change and purge."""
        draft_pk = self.draft.pk

        self.game.dire_team = None
        self.game.save()

        self.assertFalse(HeroDraft.objects.filter(pk=draft_pk).exists())

    def test_saving_game_with_unchanged_teams_preserves_herodraft(self):
        """Status / next_game / scheduling changes must NOT nuke the draft —
        only actual team-slot changes do."""
        draft_pk = self.draft.pk

        self.game.status = "live"
        self.game.swiss_record_wins = 1
        self.game.save()

        self.assertTrue(HeroDraft.objects.filter(pk=draft_pk).exists())

    def test_creating_a_game_does_not_error(self):
        """The pre_save guard must short-circuit cleanly for new (unsaved)
        Game instances — there's no prior row to compare against and no
        HeroDraft yet."""
        Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_radiant,
            dire_team=self.team_dire_corrected,
        )

    def test_game_with_no_herodraft_team_change_is_noop(self):
        """Games without a HeroDraft must change teams freely with no error
        — most bracket matches go through advance_winner before anyone
        starts a draft on them."""
        other_game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_radiant,
            dire_team=self.team_dire_original,
        )
        other_game.dire_team = self.team_dire_corrected
        other_game.save()  # must not raise
