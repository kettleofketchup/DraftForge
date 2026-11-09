"""skip_turn strategies, reassign_round_captain, check_timeout guards and pick-vs-timeout ordering (spec §2)."""

from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.functions import shuffle_draft
from app.functions.teamdraft_timeout import TIMEOUT_ACTIONS, find_swap_target, recompute_pick_phase, skip_turn
from app.models import Draft, DraftRound, Team, TeamDraftState
from app.tasks import teamdraft_tick
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


class CheckTimeoutTests(TransactionTestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="snake", grace_time_ms=1000, reserve_time_ms=2000, prefix="to")
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            self.rnd = self.fx.start(now=timezone.now() - timedelta(seconds=10))

    def check(self):
        return async_to_sync(teamdraft_tick.check_timeout)(self.fx.draft.pk)

    def test_expiry_debits_reserve_sets_timed_out_and_skips(self):
        nxt = self.check()
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.captain_id, self.fx.teams[1].captain_id)
        self.rnd.refresh_from_db()
        team = Team.objects.get(pk=self.fx.team_of(self.rnd.captain).pk)
        self.assertEqual(team.draft_reserve_ms, 0)
        self.assertEqual(self.rnd.reserve_used_ms, 2000)
        self.assertGreaterEqual(self.rnd.pick_duration_ms, 10000)
        self.assertEqual(self.rnd.pick_number, 2)
        ev = self.fx.events("pick_timed_out").get()
        self.assertEqual(ev.payload["captain_id"], self.rnd.captain_id)
        self.assertGreaterEqual(ev.payload["elapsed_ms"], 10000)
        self.assertEqual(ev.payload["reserve_used_ms"], 2000, "debit capped at the pool, same value as the round field")
        self.assertEqual(self.fx.events("pick_skipped").count(), 1)

    def test_not_yet_expired_is_noop(self):
        self.rnd.started_at = timezone.now() - timedelta(seconds=2); self.rnd.save()
        self.assertIsNone(self.check())
        self.rnd.refresh_from_db()
        self.assertIsNone(self.rnd.timed_out_at)

    def test_paused_draft_never_fires(self):
        draft = Draft.objects.get(pk=self.fx.draft.pk)
        draft.state = TeamDraftState.PAUSED; draft.paused_at = timezone.now(); draft.save()
        self.assertIsNone(self.check())
        self.rnd.refresh_from_db()
        self.assertIsNone(self.rnd.timed_out_at)
        self.assertFalse(self.fx.events("pick_timed_out").exists())

    def test_last_slot_fires_exactly_once_over_six_ticks(self):
        for _ in range(15):
            self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        last = self.fx.draft.active_round
        last.started_at = timezone.now() - timedelta(seconds=10); last.save()
        reserve_before = Team.objects.get(pk=self.fx.team_of(last.captain).pk).draft_reserve_ms
        for _ in range(6):
            self.assertIsNone(self.check())
        self.assertEqual(self.fx.events("pick_timed_out").count(), 1)
        self.assertEqual(self.fx.events("pick_skip_unavailable").count(), 1)
        last.refresh_from_db()
        self.assertIsNotNone(last.timed_out_at)
        self.assertEqual(last.reserve_used_ms, reserve_before)
        self.assertEqual(Team.objects.get(pk=self.fx.team_of(last.captain).pk).draft_reserve_ms, 0)

    def test_pick_after_last_slot_timeout_does_not_double_count(self):
        for _ in range(15):
            self.fx.pick(self.fx.draft.active_round, self.fx.staff)
        last = self.fx.draft.active_round
        last.started_at = timezone.now() - timedelta(seconds=10); last.save()
        self.assertIsNone(self.check())
        last.refresh_from_db()
        after_timeout = (last.pick_duration_ms, last.reserve_used_ms)
        self.assertEqual(self.fx.pick(last, self.fx.staff).status_code, 201)
        last.refresh_from_db()
        self.assertEqual((last.pick_duration_ms, last.reserve_used_ms), after_timeout)
        self.assertIsNotNone(last.completed_at)
        self.assertEqual(Draft.objects.get(pk=self.fx.draft.pk).state, TeamDraftState.COMPLETED)

    def test_timeout_after_staff_pick_during_pause_and_resume(self):
        client = APIClient()
        client.force_authenticate(self.fx.staff)
        base = f"/api/draft/{self.fx.draft.pk}"
        self.assertEqual(client.post(f"{base}/pause/").status_code, 200)
        self.assertEqual(self.fx.pick(self.rnd, self.fx.staff).status_code, 201)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            self.assertEqual(client.post(f"{base}/resume/").status_code, 200)
        draft = Draft.objects.get(pk=self.fx.draft.pk)
        draft.state, draft.resuming_until = TeamDraftState.DRAFTING, None
        draft.save()
        rnd2 = draft.active_round
        self.assertEqual(rnd2.grace_time_ms, 1000)
        rnd2.started_at = timezone.now() - timedelta(seconds=10); rnd2.save()
        nxt = self.check()
        self.assertIsNotNone(nxt)
        self.assertEqual((nxt.pick_number, nxt.captain_id), (2, self.fx.teams[2].captain_id))


class PickTimeoutOrderingTests(TransactionTestCase):
    """The Draft lock serialises pick vs. timeout; each ordering is pinned deterministically.
    (No threaded variant: the unit-test DB is shared-cache in-memory SQLite, where a second BEGIN IMMEDIATE gets SQLITE_LOCKED instead of waiting.)"""

    def setUp(self):
        self.fx = TimedDraftFixture(style="snake", grace_time_ms=1000, reserve_time_ms=1000, prefix="cc")
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            self.rnd = self.fx.start(now=timezone.now() - timedelta(seconds=5))

    def check(self):
        return async_to_sync(teamdraft_tick.check_timeout)(self.fx.draft.pk)

    def test_pick_lands_first_then_timeout_is_noop(self):
        self.assertEqual(self.fx.pick(self.rnd, self.rnd.captain).status_code, 201)
        self.assertIsNone(self.check())
        self.assertFalse(self.fx.events("pick_skipped").exists())
        self.assertEqual(self.fx.events("round_started").filter(payload__pick_number=2).count(), 1)

    def test_timeout_lands_first_then_pick_on_deferred_round_is_409(self):
        self.assertIsNotNone(self.check())
        r = self.fx.pick(self.rnd, self.rnd.captain)
        self.assertEqual((r.status_code, r.data["code"]), (409, "not_active_round"))
        self.rnd.refresh_from_db()
        self.assertIsNone(self.rnd.choice)
        self.assertFalse(self.fx.events("player_picked").exists())
        self.assertEqual(self.fx.events("round_started").filter(payload__pick_number=1).count(), 2)

    def test_stale_pre_read_writes_nothing(self):
        stale = (self.rnd.pk, self.rnd.started_at - timedelta(seconds=1))
        with patch("app.tasks.teamdraft_tick.read_timeout_candidate", return_value=stale):
            self.assertIsNone(self.check())
        self.rnd.refresh_from_db()
        self.assertIsNone(self.rnd.timed_out_at)
        self.assertFalse(self.fx.events("pick_timed_out").exists())


class ShufflePickTimeoutOrderingTests(TransactionTestCase):
    """Shuffle skip keeps the round pk; the locked re-read must re-check the captain."""

    def setUp(self):
        self.fx = TimedDraftFixture(
            style="shuffle", grace_time_ms=1000, reserve_time_ms=1000, prefix="sr", captain_mmrs=CAPTAIN_MMRS
        )
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            self.rnd = self.fx.start(now=timezone.now() - timedelta(seconds=5))

    def test_skip_lands_between_auth_and_lock_then_skipped_captain_pick_is_refused(self):
        captain_a, captain_b = self.fx.teams[0].captain, self.fx.teams[1].captain
        self.assertEqual(self.rnd.captain_id, captain_a.pk)
        b_members = set(self.fx.team_of(captain_b).members.values_list("pk", flat=True))

        def skip_then_deny(*_args: object) -> bool:
            self.assertIsNotNone(async_to_sync(teamdraft_tick.check_timeout)(self.fx.draft.pk))
            return False

        with patch("app.functions.draft_picks.can_edit_tournament", side_effect=skip_then_deny):
            r = self.fx.pick(self.rnd, captain_a)
        self.assertEqual((r.status_code, r.data["code"]), (409, "not_active_round"))
        self.rnd.refresh_from_db()
        self.assertEqual(self.rnd.captain_id, captain_b.pk)
        self.assertIsNone(self.rnd.choice)
        self.assertEqual(set(self.fx.team_of(captain_b).members.values_list("pk", flat=True)), b_members)
        self.assertFalse(self.fx.events("player_picked").exists())
        self.assertEqual(self.fx.events("pick_skipped").count(), 1)
