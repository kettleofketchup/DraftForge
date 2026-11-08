"""Team-draft timer lifecycle: helpers, endpoints, pick matrix, undo, auto-pause, tick payload (spec §2)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.functions import teamdraft
from app.models import Team, TeamDraftState
from app.tasks.draft_tick import evaluate_client_pick_time
from app.tests.teamdraft_fixtures import TimedDraftFixture


class LifecycleHelperTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture()

    def test_team_payload_denormalises_with_role_prefix(self):
        team = self.fx.teams[0]
        p = teamdraft.team_payload(team, "skipped")
        self.assertEqual(
            set(p),
            {
                "skipped_captain_id",
                "skipped_captain_name",
                "skipped_captain_avatar_url",
                "skipped_team_id",
                "skipped_team_name",
            },
        )
        self.assertEqual(p["skipped_captain_id"], team.captain.pk)
        self.assertEqual(teamdraft.team_payload(None)["captain_id"], None)

    def test_emit_event_broadcasts_only_after_commit(self):
        with patch("app.functions.teamdraft.broadcast_event") as mock_bc:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                ev = teamdraft.emit_event(
                    self.fx.draft,
                    "captain_ready",
                    teamdraft.team_payload(self.fx.teams[0]),
                )
                mock_bc.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            mock_bc.assert_called_once_with(ev)
        self.assertEqual(
            ev.payload["pick_number"], 1, "emit_event fills the common pick_number"
        )

    def test_start_draft_arms_first_round_and_emits_round_started(self):
        now = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            rnd = self.fx.start(now=now)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.DRAFTING)
        self.assertEqual(rnd.started_at, now)
        self.assertEqual(rnd.grace_time_ms, 30000)
        self.assertTrue(self.fx.draft.clock_armed)
        ev = self.fx.events("round_started").get()
        self.assertEqual(ev.payload["pick_number"], 1)
        self.assertEqual(ev.payload["reserve_ms"], 30000)
        self.assertEqual(ev.payload["captain_id"], rnd.captain_id)

    def test_activate_round_while_paused_leaves_started_at_null(self):
        self.fx.start()
        self.fx.draft.state = TeamDraftState.PAUSED
        self.fx.draft.save()
        rnd = self.fx.round(2)
        rnd.skip_count = 2
        rnd.save()
        teamdraft.activate_round(
            self.fx.draft, rnd, self.fx.options, now=timezone.now(), armed=False
        )
        rnd.refresh_from_db()
        self.assertIsNone(rnd.started_at)
        self.assertEqual(rnd.skip_count, 2, "activation never resets cumulative fields")
        self.assertFalse(
            self.fx.events("round_started").filter(payload__pick_number=2).exists()
        )

    def test_record_pick_timing_is_cumulative_and_debits_reserve_past_grace(self):
        rnd = self.fx.start()
        team = self.fx.team_of(rnd.captain)
        rnd.pick_duration_ms, rnd.reserve_used_ms = 1000, 0
        teamdraft.record_pick_timing(
            rnd,
            team,
            completed_at=rnd.started_at + timedelta(seconds=35),
            effective_pick_time=rnd.started_at + timedelta(seconds=35),
        )
        rnd.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(rnd.pick_duration_ms, 36000)
        self.assertEqual(rnd.reserve_used_ms, 5000)
        self.assertEqual(team.draft_reserve_ms, 25000)
        self.assertIsNotNone(rnd.completed_at)

    def test_record_pick_timing_noop_when_unarmed(self):
        rnd = self.fx.round(1)
        team = self.fx.team_of(rnd.captain)
        teamdraft.record_pick_timing(
            rnd, team, completed_at=timezone.now(), effective_pick_time=timezone.now()
        )
        rnd.refresh_from_db()
        self.assertIsNone(rnd.pick_duration_ms)
        self.assertIsNone(rnd.completed_at)

    def test_record_pick_timing_after_timeout_only_sets_completed_at(self):
        rnd = self.fx.start()
        team = self.fx.team_of(rnd.captain)
        rnd.pick_duration_ms, rnd.reserve_used_ms, rnd.timed_out_at = (
            61000,
            30000,
            timezone.now(),
        )
        rnd.save()
        team.draft_reserve_ms = 0
        team.save()
        teamdraft.record_pick_timing(
            rnd,
            team,
            completed_at=timezone.now(),
            effective_pick_time=rnd.started_at + timedelta(seconds=90),
        )
        rnd.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(
            (rnd.pick_duration_ms, rnd.reserve_used_ms, team.draft_reserve_ms),
            (61000, 30000, 0),
        )
        self.assertIsNotNone(rnd.completed_at)

    def test_record_pick_timing_caps_debit_at_pool_and_falls_back_for_null_pool(self):
        rnd = self.fx.start()
        team = self.fx.team_of(rnd.captain)
        team.draft_reserve_ms = None
        teamdraft.record_pick_timing(
            rnd,
            team,
            completed_at=timezone.now(),
            effective_pick_time=rnd.started_at + timedelta(seconds=90),
            default_reserve_ms=30000,
        )
        rnd.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual((rnd.reserve_used_ms, team.draft_reserve_ms), (30000, 0))

    def test_start_draft_seeds_null_reserve_pools(self):
        Team.objects.filter(tournament=self.fx.tournament).update(draft_reserve_ms=None)
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.start()
        self.assertEqual(
            set(
                Team.objects.filter(tournament=self.fx.tournament).values_list(
                    "draft_reserve_ms", flat=True
                )
            ),
            {30000},
        )
        self.assertEqual(
            self.fx.events("round_started").get().payload["reserve_ms"], 30000
        )

    def test_advance_after_pick_while_paused_activates_unarmed_with_grace(self):
        rnd = self.fx.start()
        nxt = self.fx.round(2)
        nxt.timed_out_at = timezone.now()
        nxt.save()
        rnd.choice = self.fx.players[0]
        rnd.save()
        self.fx.draft.state = TeamDraftState.PAUSED
        self.fx.draft.save()
        with self.captureOnCommitCallbacks(execute=True):
            got = teamdraft.advance_after_pick(
                self.fx.draft, self.fx.options, now=timezone.now(), activate=True
            )
        got.refresh_from_db()
        self.assertEqual(
            (got.pick_number, got.started_at, got.grace_time_ms, got.timed_out_at),
            (2, None, 30000, None),
        )
        self.assertFalse(
            self.fx.events("round_started").filter(payload__pick_number=2).exists()
        )

    def test_evaluate_client_pick_time_rejects_future_and_stale(self):
        now = timezone.now()
        kw = {"system": "teamdraft", "subsystem": "timer"}
        self.assertEqual(
            evaluate_client_pick_time(now, now + timedelta(seconds=1), 1, **kw)[1],
            "server_now",
        )
        self.assertEqual(
            evaluate_client_pick_time(now, now - timedelta(seconds=3), 1, **kw)[1],
            "server_now",
        )
        self.assertEqual(
            evaluate_client_pick_time(now, now - timedelta(seconds=1), 1, **kw)[1],
            "client",
        )

    def test_evaluate_client_pick_time_tags_logs_with_caller_taxonomy(self):
        now = timezone.now()
        with patch("app.tasks.draft_tick.log") as mock_log:
            evaluate_client_pick_time(
                now,
                now + timedelta(seconds=1),
                1,
                system="teamdraft",
                subsystem="timer",
            )
        kwargs = mock_log.warning.call_args.kwargs
        self.assertEqual(
            (mock_log.warning.call_args.args[0], kwargs["system"], kwargs["subsystem"]),
            ("pick_time_in_future", "teamdraft", "timer"),
        )
