"""Tests for the pre_save signal that resets a stale HeroDraft when the
underlying Game's teams change (issue #235).

Scenario the signal exists to handle: an admin sets a bracket match's
teams incorrectly, a HeroDraft is created for that match, then the
bracket is reset/re-saved with the correct teams. Without the signal,
the DraftTeam rows still FK the previous teams and the draft UI keeps
showing the wrong captains; no client reload recovers it.

The signal resets the draft **in place** — same HeroDraft pk, repointed
DraftTeam.tournament_team FKs, cleared rounds/state, kept event-log
history — so any external reference to the draft (Discord-posted
``/herodraft/{pk}/`` link, etc.) keeps working.

Edge case: when a Game slot is cleared to NULL (the in-place reset can't
repoint to None because DraftTeam.tournament_team is non-nullable) the
signal falls back to deleting the HeroDraft.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftEvent,
    HeroDraftRound,
    HeroDraftState,
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


class HeroDraftResetOnGameTeamChangeTest(TestCase):
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
        self.draft = HeroDraft.objects.create(
            game=self.game,
            state=HeroDraftState.DRAFTING,
        )
        self.dt_radiant = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team_radiant,
            is_ready=True,
            is_connected=True,
            reserve_time_remaining=42000,
        )
        self.dt_dire = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team_dire_original,
            is_ready=True,
            is_connected=True,
            reserve_time_remaining=37000,
        )

        # A pick from the wrong captain, and an audit-log event.
        HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.dt_dire,
            action_type="pick",
            state="completed",
            round_number=1,
            hero_id=1,
        )
        HeroDraftEvent.objects.create(
            draft=self.draft,
            event_type="captain_connected",
            metadata={"who": "wrong_captain"},
        )

    def test_changing_dire_team_resets_draft_in_place(self):
        """The exact reproduction from issue #235. After the bracket is
        re-saved with the correct dire team:
        - The HeroDraft pk is preserved (Discord links still work).
        - The dire DraftTeam now points at the corrected team, so its
          captain resolves to the right user.
        - Picks/bans from the wrong captain are wiped.
        - DraftTeam ready/connected flags reset (captains must re-join).
        - Draft state returns to WAITING_FOR_CAPTAINS."""
        draft_pk = self.draft.pk

        self.game.dire_team = self.team_dire_corrected
        self.game.save()

        # Same row — pk preserved.
        self.assertTrue(HeroDraft.objects.filter(pk=draft_pk).exists())
        draft = HeroDraft.objects.get(pk=draft_pk)
        self.assertEqual(draft.state, HeroDraftState.WAITING_FOR_CAPTAINS)
        self.assertIsNone(draft.roll_winner)
        self.assertIsNone(draft.paused_at)
        self.assertIsNone(draft.resuming_until)
        self.assertFalse(draft.is_manual_pause)

        # DraftTeams repointed to current Game teams.
        self.dt_radiant.refresh_from_db()
        self.dt_dire.refresh_from_db()
        self.assertEqual(self.dt_radiant.tournament_team, self.team_radiant)
        self.assertEqual(self.dt_dire.tournament_team, self.team_dire_corrected)

        # Ready / connected flags reset (captains must re-join).
        self.assertFalse(self.dt_radiant.is_ready)
        self.assertFalse(self.dt_radiant.is_connected)
        self.assertEqual(self.dt_radiant.reserve_time_remaining, 90000)
        self.assertFalse(self.dt_dire.is_ready)
        self.assertFalse(self.dt_dire.is_connected)
        self.assertEqual(self.dt_dire.reserve_time_remaining, 90000)

        # Picks/bans from the wrong captain are gone.
        self.assertFalse(HeroDraftRound.objects.filter(draft_id=draft_pk).exists())

    def test_changing_radiant_team_resets_draft_in_place(self):
        """Same reset fires when the radiant slot is the one rewritten
        (e.g. advance_winner flips which team feeds the radiant slot of
        this downstream match)."""
        draft_pk = self.draft.pk
        other_radiant = _make_team(
            self.tournament, "Other Radiant", _make_user("other_cap")
        )

        self.game.radiant_team = other_radiant
        self.game.save()

        self.assertTrue(HeroDraft.objects.filter(pk=draft_pk).exists())
        self.dt_radiant.refresh_from_db()
        self.assertEqual(self.dt_radiant.tournament_team, other_radiant)

    def test_clearing_team_to_none_falls_back_to_delete(self):
        """DraftTeam.tournament_team is non-nullable, so the in-place reset
        can't repoint a slot to None. When a Game slot is cleared
        (e.g. mid-bracket-reset, before winners are re-entered), fall back
        to deleting the HeroDraft. Once the bracket is re-saved with real
        teams, create_herodraft rebuilds. The Discord link 404s in this
        narrow window — better than leaving stale FK state."""
        draft_pk = self.draft.pk

        self.game.dire_team = None
        self.game.save()

        self.assertFalse(HeroDraft.objects.filter(pk=draft_pk).exists())
        self.assertFalse(
            DraftTeam.objects.filter(draft_id=draft_pk).exists(),
            "DraftTeam rows should cascade-delete with HeroDraft",
        )

    def test_reset_keeps_herodraft_event_history(self):
        """HeroDraftEvent rows survive the reset — they're the audit trail
        of the wrong setup ever happening. Clearing them would hide that."""
        draft_pk = self.draft.pk
        events_before = list(
            HeroDraftEvent.objects.filter(draft_id=draft_pk).values_list("pk", flat=True)
        )
        self.assertTrue(events_before)

        self.game.dire_team = self.team_dire_corrected
        self.game.save()

        events_after = list(
            HeroDraftEvent.objects.filter(draft_id=draft_pk).values_list("pk", flat=True)
        )
        self.assertEqual(set(events_before), set(events_after))

    def test_saving_game_with_unchanged_teams_preserves_draft_state(self):
        """Status / next_game / scheduling changes must NOT reset the draft
        — only actual team-slot changes do."""
        draft_pk = self.draft.pk

        self.game.status = "live"
        self.game.swiss_record_wins = 1
        self.game.save()

        draft = HeroDraft.objects.get(pk=draft_pk)
        self.assertEqual(draft.state, HeroDraftState.DRAFTING)
        self.dt_dire.refresh_from_db()
        self.assertTrue(self.dt_dire.is_ready)
        self.assertEqual(self.dt_dire.tournament_team, self.team_dire_original)
        self.assertTrue(HeroDraftRound.objects.filter(draft_id=draft_pk).exists())

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

    def test_reset_clears_pick_order_and_side_choices(self):
        """``do_submit_choice`` rejects when ``is_first_pick`` or
        ``is_radiant`` is non-null ("Pick order already chosen" / "Side
        already chosen"). After a team-swap reset the new captains must
        be able to roll + choose again — so both fields go back to None,
        matching what the user-facing ``reset_draft`` view does."""
        self.dt_radiant.is_first_pick = True
        self.dt_radiant.is_radiant = True
        self.dt_radiant.save()
        self.dt_dire.is_first_pick = False
        self.dt_dire.is_radiant = False
        self.dt_dire.save()

        self.game.dire_team = self.team_dire_corrected
        self.game.save()

        self.dt_radiant.refresh_from_db()
        self.dt_dire.refresh_from_db()
        self.assertIsNone(self.dt_radiant.is_first_pick)
        self.assertIsNone(self.dt_radiant.is_radiant)
        self.assertIsNone(self.dt_dire.is_first_pick)
        self.assertIsNone(self.dt_dire.is_radiant)

    def test_reset_broadcasts_draft_reset_event_with_same_pk(self):
        """Connected HeroDraftConsumer clients learn the draft was reset
        via the existing channel group (``herodraft_{pk}``). They can
        refetch and stay on the same draft URL since the pk is preserved.

        The broadcast is deferred to ``transaction.on_commit`` so clients
        never see pre-commit data; ``captureOnCommitCallbacks(execute=True)``
        runs the deferred callbacks at block exit (Django ``TestCase``
        rolls the surrounding transaction back, so on_commit otherwise
        never fires)."""
        draft_pk = self.draft.pk

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        with patch(
            "channels.layers.get_channel_layer", return_value=mock_layer
        ), self.captureOnCommitCallbacks(execute=True):
            self.game.dire_team = self.team_dire_corrected
            self.game.save()

        # Draft row still exists.
        self.assertTrue(HeroDraft.objects.filter(pk=draft_pk).exists())
        # And the broadcast fired.
        mock_layer.group_send.assert_called_once()
        group_name, payload = mock_layer.group_send.call_args.args
        self.assertEqual(group_name, f"herodraft_{draft_pk}")
        self.assertEqual(payload["type"], "herodraft.event")
        self.assertEqual(payload["event_type"], "draft_reset")
        self.assertEqual(payload["metadata"]["reason"], "teams_changed")
        self.assertEqual(payload["metadata"]["game_id"], self.game.pk)

    def test_broadcast_is_deferred_until_transaction_commit(self):
        """Regression for the in-transaction race: if the WS broadcast
        fires while ``save_bracket``'s outer ``@transaction.atomic`` is
        still open, clients refetch and read pre-reset rows (or repopulate
        cacheops with them), defeating the whole reset. The broadcast must
        be scheduled on commit, not run synchronously inside the signal."""
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        with patch(
            "channels.layers.get_channel_layer", return_value=mock_layer
        ), self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.game.dire_team = self.team_dire_corrected
            self.game.save()
            # Inside the block: the signal has run and the rows are
            # updated, but the broadcast must NOT have fired yet. (The
            # ``callbacks`` list is only populated at block exit, so
            # length is asserted after the ``with``.)
            mock_layer.group_send.assert_not_called()

        # ``execute=False`` leaves the captured callbacks unrun, so the
        # broadcast still has not fired even after the block. The list
        # has more than one entry because ``invalidate_after_commit`` also
        # registers an on_commit hook — we only care that *the broadcast*
        # was deferred, not the precise count.
        self.assertGreaterEqual(len(callbacks), 1)
        mock_layer.group_send.assert_not_called()

    def test_clearing_team_to_none_broadcasts_draft_invalidated(self):
        """The delete-fallback path uses event_type=draft_invalidated so the
        frontend can show a different message from the in-place reset
        (where the same draft URL keeps working)."""
        draft_pk = self.draft.pk

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        with patch(
            "channels.layers.get_channel_layer", return_value=mock_layer
        ), self.captureOnCommitCallbacks(execute=True):
            self.game.dire_team = None
            self.game.save()

        self.assertFalse(HeroDraft.objects.filter(pk=draft_pk).exists())
        mock_layer.group_send.assert_called_once()
        group_name, payload = mock_layer.group_send.call_args.args
        self.assertEqual(group_name, f"herodraft_{draft_pk}")
        self.assertEqual(payload["event_type"], "draft_invalidated")

    def test_reset_still_succeeds_when_channel_layer_send_fails(self):
        """The in-place reset is the integrity guarantee; the WS broadcast
        is best-effort. A channel layer failure must NOT block the reset
        or raise."""
        draft_pk = self.draft.pk

        failing_layer = MagicMock()
        failing_layer.group_send.side_effect = RuntimeError("channel down")
        with patch(
            "channels.layers.get_channel_layer", return_value=failing_layer
        ), self.captureOnCommitCallbacks(execute=True):
            self.game.dire_team = self.team_dire_corrected
            self.game.save()  # must not raise

        # Reset still applied to the row.
        draft = HeroDraft.objects.get(pk=draft_pk)
        self.assertEqual(draft.state, HeroDraftState.WAITING_FOR_CAPTAINS)
        self.dt_dire.refresh_from_db()
        self.assertEqual(self.dt_dire.tournament_team, self.team_dire_corrected)
