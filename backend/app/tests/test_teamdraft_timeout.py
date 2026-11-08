"""skip_turn strategies, reassign_round_captain, check_timeout guards and pick-vs-timeout ordering (spec §2)."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.functions import shuffle_draft
from app.functions.teamdraft_timeout import TIMEOUT_ACTIONS, find_swap_target, recompute_pick_phase, skip_turn
from app.models import DraftRound, TeamDraftState
from app.tests.teamdraft_fixtures import TimedDraftFixture

CAPTAIN_MMRS = [1000, 2000, 3000, 4000]  # teams[0] is lowest -> shuffle's first captain, no tie roll


class ReassignRoundCaptainTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="shuffle", captain_mmrs=CAPTAIN_MMRS)

    def test_reassigns_lowest_eligible_excluding_given_team_with_reason(self):
        rnd = self.fx.round(1)
        self.assertEqual(rnd.captain, self.fx.teams[0].captain)
        rnd.was_tie = True
        rnd.tie_roll_data = {"x": 1}
        rnd.save()
        with patch("app.functions.shuffle_draft.broadcast_event") as mock_bc, self.captureOnCommitCallbacks(execute=True):
            tie = shuffle_draft.reassign_round_captain(self.fx.draft, rnd, {self.fx.teams[0].pk}, reason="timeout_skip")
        rnd.refresh_from_db()
        self.assertIsNone(tie)
        self.assertEqual(rnd.captain, self.fx.teams[1].captain)
        self.assertFalse(rnd.was_tie)
        self.assertIsNone(rnd.tie_roll_data)
        ev = self.fx.events("captain_assigned").get()
        self.assertEqual(ev.payload["reason"], "timeout_skip")
        self.assertEqual(ev.payload["pick_number"], 1)
        mock_bc.assert_called_once()

    def test_no_eligible_team_returns_none_and_leaves_round(self):
        rnd = self.fx.round(1)
        result = shuffle_draft.reassign_round_captain(self.fx.draft, rnd, {t.pk for t in self.fx.teams})
        self.assertIsNone(result)
        rnd.refresh_from_db()
        self.assertEqual(rnd.captain, self.fx.teams[0].captain)
        self.assertFalse(self.fx.events("captain_assigned").exists())

    def test_assign_next_wraps_reassign_without_exclusions_and_no_reason(self):
        with self.captureOnCommitCallbacks(execute=True):
            shuffle_draft.assign_next_shuffle_captain(self.fx.draft)
        rnd2 = self.fx.round(2)
        self.assertEqual(rnd2.captain, self.fx.teams[0].captain)
        self.assertNotIn("reason", self.fx.events("captain_assigned").get().payload)


def expire(rnd: DraftRound) -> None:
    rnd.timed_out_at = timezone.now()
    rnd.save(update_fields=["timed_out_at"])


class SkipTurnSnakeTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="snake")
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.fx.start()

    def captain_order(self):
        return [r.captain_id for r in self.fx.draft.draft_rounds.order_by("pick_number")]

    def test_registry_has_only_skip_turn(self):
        self.assertEqual(set(TIMEOUT_ACTIONS), {"skip_turn"})
        self.assertIs(TIMEOUT_ACTIONS["skip_turn"], skip_turn)

    def test_recompute_pick_phase_matches_build_rounds(self):
        for rnd in self.fx.draft.draft_rounds.all():
            self.assertEqual(recompute_pick_phase(rnd.pick_number, 4), rnd.pick_phase)

    def test_first_pick_timeout_swaps_with_next_and_defers(self):
        a, b, c, d = [t.captain_id for t in self.fx.teams]
        rnd1 = self.fx.round(1); expire(rnd1)
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(self.fx.draft, rnd1)
        self.assertEqual(self.captain_order()[:4], [b, a, c, d])
        self.assertEqual(nxt.pick_number, 1)
        self.assertEqual(nxt.captain_id, b)
        self.assertIsNotNone(nxt.started_at)
        rnd1.refresh_from_db()
        self.assertEqual((rnd1.pick_number, rnd1.skip_count), (2, 1))
        self.assertIsNone(rnd1.started_at); self.assertIsNone(rnd1.timed_out_at)
        ev = self.fx.events("pick_skipped").get()
        self.assertEqual(ev.payload["skipped_captain_id"], a)
        self.assertEqual(ev.payload["next_captain_id"], b)
        self.assertEqual((ev.payload["from_pick_number"], ev.payload["to_pick_number"], ev.payload["deferred_to_pick_number"]), (1, 1, 2))
        self.assertEqual(self.fx.events("round_started").filter(payload__pick_number=1).count(), 2)

    def test_double_skip_slides_again(self):
        a, b, c, d = [t.captain_id for t in self.fx.teams]
        rnd = self.fx.round(1); expire(rnd)
        with self.captureOnCommitCallbacks(execute=True):
            skip_turn(self.fx.draft, rnd)
        # B picks at 1, A is active at 2 and times out again
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        rnd.refresh_from_db(); expire(rnd)
        with self.captureOnCommitCallbacks(execute=True):
            skip_turn(self.fx.draft, rnd)
        self.assertEqual(self.captain_order()[:4], [b, c, a, d])
        rnd.refresh_from_db()
        self.assertEqual((rnd.pick_number, rnd.skip_count), (3, 2))

    def test_last_team_double_pick_is_skipped_over_same_captain(self):
        a, b, c, d = [t.captain_id for t in self.fx.teams]
        for _ in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        rnd4 = self.fx.draft.active_round
        self.assertEqual((rnd4.pick_number, rnd4.captain_id, self.fx.round(5).captain_id), (4, d, d))
        expire(rnd4)
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(self.fx.draft, rnd4)
        self.assertEqual(nxt.captain_id, c, "original pick 6 (C) renumbered 4")
        self.assertEqual(nxt.pick_number, 4)
        order = self.captain_order()
        self.assertEqual(order[3:6], [c, d, d])
        self.assertEqual(self.fx.round(5).pick_phase, 2)
        # C picks at 4; D times out again at the new 5 -> swaps with B (original pick 7)
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        rnd5 = self.fx.draft.active_round
        self.assertEqual((rnd5.pick_number, rnd5.captain_id), (5, d))
        expire(rnd5)
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(self.fx.draft, rnd5)
        self.assertEqual((nxt.pick_number, nxt.captain_id), (5, b))
        self.assertEqual(self.captain_order()[4:8], [b, d, d, a])

    def test_swap_then_undo_keeps_deferred_captain(self):
        a, b, c, d = [t.captain_id for t in self.fx.teams]
        rnd1 = self.fx.round(1); expire(rnd1)
        with self.captureOnCommitCallbacks(execute=True):
            skip_turn(self.fx.draft, rnd1)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.fx.pick(self.fx.draft.active_round, self.fx.staff).status_code, 201)   # B picks at 1
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.fx.undo(self.fx.staff).status_code, 200)
        self.assertEqual(self.captain_order()[:4], [b, a, c, d])
        rnd1.refresh_from_db()
        self.assertEqual((rnd1.pick_number, rnd1.captain_id, rnd1.skip_count), (2, a, 1))
        self.assertIsNone(rnd1.started_at)
        self.assertIsNotNone(self.fx.round(1).started_at, "undone round re-armed")

    def test_staff_picked_later_round_is_skipped_over(self):
        rnd2 = self.fx.round(2)
        rnd2.choice = self.fx.players[0]; rnd2.save()   # models a round picked before the clock was armed
        rnd1 = self.fx.round(1); expire(rnd1)
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(self.fx.draft, rnd1)
        self.assertEqual(nxt.captain_id, self.fx.teams[2].captain_id)
        self.assertEqual(nxt.pick_number, 1)
        rnd2.refresh_from_db()
        self.assertEqual(rnd2.pick_number, 2, "picked round keeps its number")

    def test_no_target_is_noop_with_event_and_round_stays_expired(self):
        for _ in range(15):
            with self.captureOnCommitCallbacks(execute=True):
                self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        last = self.fx.draft.active_round
        expire(last)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(skip_turn(self.fx.draft, last))
        last.refresh_from_db()
        self.assertIsNotNone(last.timed_out_at)
        self.assertEqual(last.skip_count, 0)
        self.assertEqual(self.fx.events("pick_skip_unavailable").get().payload["captain_id"], last.captain_id)
        self.assertFalse(self.fx.events("pick_skipped").exists())

    def test_only_same_captain_rounds_remain_is_noop(self):
        # Review Focus 4: D at pick 4, pick 5 also D, picks 6-8 already picked
        for _ in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        for n in range(6, 17):
            r = self.fx.round(n); r.choice = self.fx.players[n - 1]; r.save()
        rnd4 = self.fx.draft.active_round
        self.assertIsNone(find_swap_target(self.fx.draft, rnd4))
        expire(rnd4)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(skip_turn(self.fx.draft, rnd4))
        self.assertEqual(self.fx.round(5).captain_id, rnd4.captain_id)
        self.assertTrue(self.fx.events("pick_skip_unavailable").exists())

    def test_draft_terminates_with_full_pick_counts_after_skips(self):
        for _ in range(16):
            active = self.fx.draft.active_round
            if active.pick_number in (1, 5):
                expire(active)
                with self.captureOnCommitCallbacks(execute=True):
                    skip_turn(self.fx.draft, active)
                active = self.fx.draft.active_round
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.fx.pick(active, self.fx.staff).status_code, 201)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.COMPLETED)
        for team in self.fx.teams:
            self.assertEqual(self.fx.draft.draft_rounds.filter(captain=team.captain, choice__isnull=False).count(), 4)


class SkipTurnShuffleTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="shuffle", captain_mmrs=CAPTAIN_MMRS)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.fx.start()

    def test_timeout_reselects_same_round_and_resets_timing(self):
        rnd = self.fx.round(1)
        rnd.pick_duration_ms, rnd.reserve_used_ms = 31000, 1000
        rnd.save(); expire(rnd)
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(self.fx.draft, rnd)
        self.assertEqual(nxt.pk, rnd.pk)
        rnd.refresh_from_db()
        self.assertEqual(rnd.captain, self.fx.teams[1].captain)
        self.assertEqual((rnd.pick_duration_ms, rnd.reserve_used_ms, rnd.skip_count), (0, 0, 1))
        self.assertIsNotNone(rnd.started_at)
        events = list(self.fx.draft.events.order_by("pk").values_list("event_type", flat=True))
        last_round_started = max(i for i, e in enumerate(events) if e == "round_started")
        self.assertLess(events.index("captain_assigned"), events.index("pick_skipped"))
        self.assertLess(events.index("pick_skipped"), last_round_started)
        ev = self.fx.events("pick_skipped").get()
        self.assertEqual((ev.payload["pick_duration_ms"], ev.payload["reserve_used_ms"]), (31000, 1000))
        self.assertIsNone(ev.payload["deferred_to_pick_number"])
        self.assertEqual(ev.payload["next_captain_id"], self.fx.teams[1].captain_id)
        self.assertEqual(self.fx.events("captain_assigned").filter(payload__reason="timeout_skip").count(), 1)

    def test_excluded_team_is_eligible_again_next_assignment(self):
        rnd = self.fx.round(1); expire(rnd)
        with self.captureOnCommitCallbacks(execute=True):
            skip_turn(self.fx.draft, rnd)
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        self.assertEqual(self.fx.round(2).captain, self.fx.teams[0].captain, "lowest MMR team is back in")

    def test_no_eligible_team_is_noop(self):
        for team in self.fx.teams[1:]:
            team.members.add(*self.fx.players[:4])
        rnd = self.fx.round(1); expire(rnd)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(skip_turn(self.fx.draft, rnd))
        rnd.refresh_from_db()
        self.assertEqual(rnd.captain, self.fx.teams[0].captain)
        self.assertTrue(self.fx.events("pick_skip_unavailable").exists())
