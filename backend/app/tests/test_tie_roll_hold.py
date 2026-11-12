"""A shuffle tie roll holds the next captain's clock for TIE_ROLL_HOLD_MS so every viewer sees the dice first."""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from app.functions.shuffle_draft import TIE_ROLL_HOLD_MS
from app.functions.teamdraft_timeout import skip_turn
from app.functions.teamdraft_views import teamdraft_pause, teamdraft_resume
from app.models import DraftRound
from app.tasks import teamdraft_tick
from app.tests.teamdraft_fixtures import TimedDraftFixture

HOLD = timedelta(milliseconds=TIE_ROLL_HOLD_MS)
SLACK = timedelta(seconds=2)

# teams[0] and teams[1] share the lowest MMR: after teams[0] picks a 0-MMR player they tie again.
TIED_AFTER_PICK = [1000, 1000, 3000, 4000]
# teams[0] lowest alone; once it is excluded by a timeout, teams[1] and teams[2] tie.
TIED_AFTER_SKIP = [1000, 2000, 2000, 4000]
NO_TIES = [1000, 2000, 3000, 4000]


def _started(fx: TimedDraftFixture) -> TimedDraftFixture:
    with (
        patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True),
        patch("app.functions.shuffle_draft.roll_until_winner") as roll,
    ):
        roll.side_effect = lambda teams: (teams[0], [[{"team_id": t.id, "roll": 6 - i} for i, t in enumerate(teams)]])
        fx.start()
    return fx


class TieRollHoldAfterPickTests(TestCase):
    def _pick_first_round(self, mmrs: list[int]) -> tuple[TimedDraftFixture, DraftRound, datetime]:
        fx = TimedDraftFixture(style="shuffle", captain_mmrs=mmrs, prefix="hold")
        _started(fx)
        before = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            response = fx.pick(fx.round(1), fx.staff)
        self.assertEqual(response.status_code, 201, response.data)
        return fx, fx.round(2), before

    def test_tie_after_pick_starts_next_clock_after_the_hold(self):
        fx, nxt, before = self._pick_first_round(TIED_AFTER_PICK)
        self.assertTrue(nxt.was_tie)
        self.assertGreaterEqual(nxt.started_at, before + HOLD)
        self.assertLess(nxt.started_at, before + HOLD + SLACK)

    def test_tie_event_and_round_started_carry_hold_ms(self):
        fx, nxt, _ = self._pick_first_round(TIED_AFTER_PICK)
        tie = fx.events("tie_roll").filter(payload__pick_number=2).get()
        self.assertEqual(tie.payload["hold_ms"], TIE_ROLL_HOLD_MS)
        started = fx.events("round_started").filter(payload__pick_number=2).get()
        self.assertEqual(started.payload["hold_ms"], TIE_ROLL_HOLD_MS)
        self.assertEqual(started.payload["started_at"], nxt.started_at.isoformat())

    def test_pick_response_tie_resolution_carries_hold_ms(self):
        fx = TimedDraftFixture(style="shuffle", captain_mmrs=TIED_AFTER_PICK, prefix="resp")
        _started(fx)
        with self.captureOnCommitCallbacks(execute=True):
            response: Response = fx.pick(fx.round(1), fx.staff)
        self.assertEqual(response.data["tie_resolution"]["hold_ms"], TIE_ROLL_HOLD_MS)
        self.assertEqual(response.data["tie_resolution"]["pick_number"], 2)

    def test_no_tie_after_pick_starts_next_clock_now(self):
        fx, nxt, before = self._pick_first_round(NO_TIES)
        self.assertFalse(nxt.was_tie)
        self.assertLess(nxt.started_at, before + SLACK)
        started = fx.events("round_started").filter(payload__pick_number=2).get()
        self.assertEqual(started.payload["hold_ms"], 0)

    def test_pick_during_hold_uses_no_grace_or_reserve(self):
        fx, nxt, _ = self._pick_first_round(TIED_AFTER_PICK)
        with self.captureOnCommitCallbacks(execute=True):
            response = fx.pick(nxt, fx.staff)
        self.assertEqual(response.status_code, 201, response.data)
        nxt.refresh_from_db()
        self.assertEqual((nxt.pick_duration_ms, nxt.reserve_used_ms), (0, 0))
        team = fx.team_of(nxt.captain)
        self.assertEqual(team.draft_reserve_ms, fx.options.reserve_time_ms)


class TieRollHoldAfterTimeoutTests(TestCase):
    def _skip_first_round(self, mmrs: list[int]) -> tuple[TimedDraftFixture, DraftRound, datetime]:
        fx = TimedDraftFixture(style="shuffle", captain_mmrs=mmrs, prefix="skip")
        _started(fx)
        rnd = fx.round(1)
        rnd.timed_out_at = timezone.now()
        rnd.save(update_fields=["timed_out_at"])
        before = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            nxt = skip_turn(fx.draft, rnd)
        nxt.refresh_from_db()
        return fx, nxt, before

    def test_tie_after_timeout_skip_holds_the_clock(self):
        fx, nxt, before = self._skip_first_round(TIED_AFTER_SKIP)
        self.assertTrue(nxt.was_tie)
        self.assertIn(nxt.captain, (fx.teams[1].captain, fx.teams[2].captain))
        self.assertGreaterEqual(nxt.started_at, before + HOLD)
        self.assertLess(nxt.started_at, before + HOLD + SLACK)
        tie = fx.events("tie_roll").filter(payload__pick_number=1).last()
        self.assertEqual(tie.payload["hold_ms"], TIE_ROLL_HOLD_MS)

    def test_no_tie_after_timeout_skip_starts_now(self):
        fx, nxt, before = self._skip_first_round(NO_TIES)
        self.assertFalse(nxt.was_tie)
        self.assertLess(nxt.started_at, before + SLACK)

    def test_timeout_cannot_fire_during_hold(self):
        fx = TimedDraftFixture(
            style="shuffle",
            captain_mmrs=TIED_AFTER_SKIP,
            grace_time_ms=1000,
            reserve_time_ms=1000,
            prefix="nofire",
        )
        _started(fx)
        rnd = fx.round(1)
        rnd.timed_out_at = timezone.now()
        rnd.save(update_fields=["timed_out_at"])
        with self.captureOnCommitCallbacks(execute=True):
            skip_turn(fx.draft, rnd)
        # grace + reserve (2 s) is shorter than the hold, yet the clock has not started.
        self.assertIsNone(teamdraft_tick.read_timeout_candidate(fx.draft.pk))


class TieRollHoldPauseTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="shuffle", captain_mmrs=TIED_AFTER_PICK, prefix="pause")
        _started(self.fx)
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.pick(self.fx.round(1), self.fx.staff)
        self.factory = APIRequestFactory()

    def _call(self, view, now: datetime) -> Response:
        request = self.factory.post(f"/api/draft/{self.fx.draft.pk}/x/")
        force_authenticate(request, user=self.fx.staff)
        with patch("app.functions.teamdraft_views.timezone.now", return_value=now):
            with self.captureOnCommitCallbacks(execute=True):
                return view(request, self.fx.draft.pk)

    def test_pause_and_resume_during_hold_keep_the_remaining_hold(self):
        held_start = self.fx.round(2).started_at
        t0 = timezone.now()
        self.assertEqual(self._call(teamdraft_pause, t0).status_code, 200)
        paused_for = timedelta(seconds=20)
        self.assertEqual(self._call(teamdraft_resume, t0 + paused_for).status_code, 200)
        resumed_start = self.fx.round(2).started_at
        shift = resumed_start - held_start
        # Shifted by the pause plus the resume countdown: the unspent hold is still ahead.
        self.assertGreaterEqual(shift, paused_for)
        self.assertGreater(resumed_start, t0 + paused_for)
