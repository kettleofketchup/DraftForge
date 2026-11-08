"""Team-draft timer lifecycle: helpers, endpoints, pick matrix, undo, auto-pause, tick payload (spec §2)."""

from datetime import timedelta
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from app.functions import teamdraft
from app.models import Draft, DraftEvent, DraftOptions, Team, TeamDraftState
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


class EndpointTestBase(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture()
        self.client = APIClient()

    def post(self, user, path, body=None):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                f"/api/draft/{self.fx.draft.pk}/{path}/", body or {}, format="json"
            )

    def armed(self, path="start", user=None):
        """POST start/ or resume/ with the real broadcaster patched out (no tick thread from inside a TestCase)."""
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            return self.post(user or self.fx.staff, path)


class RouteResolutionTests(TestCase):
    def test_hero_and_team_routes_resolve_to_their_own_views(self):
        for path in (
            "/api/herodraft/1/set-ready/",
            "/api/herodraft/1/pause/",
            "/api/herodraft/1/resume/",
        ):
            self.assertEqual(
                resolve(path).func.__module__, "app.functions.herodraft_views", path
            )
        for path, name in (
            ("ready", "teamdraft_set_ready"),
            ("start", "teamdraft_start"),
            ("pause", "teamdraft_pause"),
            ("resume", "teamdraft_resume"),
        ):
            func = resolve(f"/api/draft/1/{path}/").func
            self.assertEqual(
                (func.__module__, func.cls.__name__),
                ("app.functions.teamdraft_views", name),
                path,
            )


class ReadyEndpointTests(EndpointTestBase):
    def test_captain_toggles_ready_and_unready(self):
        cap = self.fx.captains[0]
        r = self.post(cap, "ready", {"ready": True})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(Team.objects.get(pk=self.fx.team_of(cap).pk).draft_is_ready)
        self.assertEqual(self.fx.events("captain_ready").get().payload["captain_id"], cap.pk)
        r = self.post(cap, "ready", {"ready": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.fx.events("captain_unready").count(), 1)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.PENDING, "ready never starts the draft")

    def test_all_ready_does_not_start_draft(self):
        for cap in self.fx.captains:
            self.post(cap, "ready", {"ready": True})
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.PENDING)

    def test_spectator_and_staff_cannot_ready(self):
        self.assertEqual(self.post(self.fx.players[0], "ready", {"ready": True}).status_code, 403)
        self.assertEqual(self.post(self.fx.staff, "ready", {"ready": True}).status_code, 403)
        self.assertFalse(self.fx.events("captain_ready").exists())

    def test_ready_outside_pending_is_400(self):
        self.armed()
        r = self.post(self.fx.captains[0], "ready", {"ready": True})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "wrong_state")


class StartEndpointTests(EndpointTestBase):
    @patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True)
    def test_start_all_ready_emits_started_by_staff(self, mock_start):
        for cap in self.fx.captains:
            self.post(cap, "ready", {"ready": True})
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.DRAFTING)
        self.assertTrue(self.fx.draft.clock_armed)
        ev = self.fx.events("draft_started_by_staff").get()
        self.assertEqual(ev.payload["actor_id"], self.fx.staff.pk)
        self.assertFalse(self.fx.events("draft_force_started").exists())
        self.assertEqual(self.fx.events("round_started").count(), 1)
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args.args[1], self.fx.draft.pk)

    @patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True)
    def test_force_start_lists_not_ready_and_arms_first_round(self, mock_start):
        self.post(self.fx.captains[0], "ready", {"ready": True})
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 200, r.data)
        ev = self.fx.events("draft_force_started").get()
        self.assertEqual({x["captain_id"] for x in ev.payload["not_ready"]}, {c.pk for c in self.fx.captains[1:]})
        self.assertEqual(set(ev.payload["not_ready"][0]), {"team_id", "team_name", "captain_id", "captain_name"})
        self.fx.draft.refresh_from_db()
        self.assertIsNotNone(self.fx.draft.active_round.started_at)

    def test_start_pending_without_rounds_is_400(self):
        self.fx.draft.draft_rounds.all().delete()
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "wrong_state")
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.PENDING)

    def test_captain_cannot_start(self):
        self.assertEqual(self.post(self.fx.captains[0], "start").status_code, 403)

    def test_start_with_timer_disabled_is_400(self):
        DraftOptions.ensure_for(self.fx.tournament, timer_enabled=False)
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "timer_disabled")

    @patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True)
    def test_start_arms_legacy_unarmed_drafting_draft(self, mock_start):
        self.fx.draft.state = TeamDraftState.DRAFTING
        self.fx.draft.save()
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db()
        self.assertTrue(self.fx.draft.clock_armed)
        self.assertEqual(self.fx.events("round_started").count(), 1)
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "already_armed")

    @patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True)
    def test_start_seeds_null_reserve_pools(self, mock_start):
        self.fx.draft.state = TeamDraftState.DRAFTING
        self.fx.draft.save()
        Team.objects.filter(tournament=self.fx.tournament).update(draft_reserve_ms=None)
        r = self.post(self.fx.staff, "start")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(set(Team.objects.filter(tournament=self.fx.tournament).values_list("draft_reserve_ms", flat=True)), {30000})
        self.assertEqual(self.fx.events("round_started").get().payload["reserve_ms"], 30000)


class PauseResumeEndpointTests(EndpointTestBase):
    def setUp(self):
        super().setUp()
        self.armed()

    def test_captain_pause_then_staff_resume_pushes_started_at(self):
        rnd = self.fx.draft.active_round
        started = rnd.started_at
        r = self.post(self.fx.captains[2], "pause")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.PAUSED)
        self.assertTrue(self.fx.draft.is_manual_pause)
        ev = self.fx.events("draft_paused").get()
        self.assertEqual(ev.payload["reason"], "manual")
        self.assertEqual(ev.payload["paused_by_id"], self.fx.captains[2].pk)
        self.assertEqual(ev.payload["captain_id"], rnd.captain_id)
        self.assertEqual(ev.payload["pick_number"], 1)

        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True) as mock_start:
            r = self.post(self.fx.staff, "resume")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db(); rnd.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.RESUMING)
        self.assertIsNone(self.fx.draft.paused_at)
        self.assertFalse(self.fx.draft.is_manual_pause)
        self.assertGreaterEqual(rnd.started_at - started, timedelta(seconds=3))
        self.assertEqual(self.fx.events("draft_resumed").get().payload["resumed_by_id"], self.fx.staff.pk)
        mock_start.assert_called_once()

    def test_resume_with_null_started_at_sets_resuming_until(self):
        self.post(self.fx.staff, "pause")
        rnd = self.fx.draft.active_round
        rnd.started_at = None
        rnd.save()
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            r = self.post(self.fx.staff, "resume")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db(); rnd.refresh_from_db()
        self.assertEqual(rnd.started_at, self.fx.draft.resuming_until)

    def test_resume_fills_missing_grace(self):
        self.post(self.fx.staff, "pause")
        rnd = self.fx.draft.active_round
        rnd.grace_time_ms = None
        rnd.save()
        self.assertEqual(self.armed("resume").status_code, 200)
        rnd.refresh_from_db()
        self.assertEqual(rnd.grace_time_ms, 30000)

    def test_pause_during_resuming_is_400(self):
        self.post(self.fx.staff, "pause")
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True):
            self.post(self.fx.staff, "resume")
        r = self.post(self.fx.staff, "pause")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "clock_not_running")

    def test_resume_while_drafting_is_400(self):
        r = self.post(self.fx.staff, "resume")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "clock_not_running")

    def test_pause_unarmed_draft_is_400(self):
        rnd = self.fx.draft.active_round
        rnd.started_at = None
        rnd.save()
        self.assertEqual(self.post(self.fx.captains[0], "pause").status_code, 400)

    def test_spectator_cannot_pause_or_resume(self):
        self.assertEqual(self.post(self.fx.players[0], "pause").status_code, 403)
        self.post(self.fx.staff, "pause")
        self.assertEqual(self.post(self.fx.players[0], "resume").status_code, 403)


class PickMatrixTests(EndpointTestBase):
    def start(self):
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            return self.fx.start()

    def test_pending_rejects_captain_and_staff(self):
        rnd = self.fx.round(1)
        for actor in (rnd.captain, self.fx.staff):
            r = self.fx.pick(rnd, actor)
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.data["code"], "draft_not_accepting_picks")

    def test_drafting_captain_non_active_round_is_409_with_active_pick_number(self):
        self.start()
        rnd3 = self.fx.round(3)
        r = self.fx.pick(rnd3, rnd3.captain)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "not_active_round")
        self.assertEqual(r.data["active_pick_number"], 1)
        r = self.fx.pick(rnd3, self.fx.staff)
        self.assertEqual(r.data["code"], "not_active_round")

    def test_paused_staff_picks_active_round_and_next_starts_unarmed(self):
        rnd = self.start()
        self.fx.draft.state = TeamDraftState.PAUSED
        self.fx.draft.paused_at = timezone.now()
        self.fx.draft.save()
        self.assertEqual(self.fx.pick(rnd, rnd.captain).status_code, 403)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.fx.pick(rnd, self.fx.staff)
        self.assertEqual(r.status_code, 201, r.data)
        nxt = self.fx.draft.active_round
        self.assertEqual(nxt.pick_number, 2)
        self.assertIsNone(nxt.started_at)
        self.assertEqual(nxt.grace_time_ms, 30000, "next round really activated (unarmed)")
        self.assertIsNone(nxt.timed_out_at)
        self.assertEqual(self.fx.events("round_started").filter(payload__pick_number=2).count(), 0)

    def test_resume_after_paused_staff_pick_arms_round_with_grace(self):
        active = self.start()
        self.assertEqual(self.post(self.fx.staff, "pause").status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.fx.pick(active, self.fx.staff).status_code, 201)
        self.assertEqual(self.armed("resume").status_code, 200)
        self.fx.draft.refresh_from_db()
        rnd = self.fx.draft.active_round
        self.assertEqual((rnd.pick_number, rnd.started_at, rnd.grace_time_ms), (2, self.fx.draft.resuming_until, 30000))

    def test_locked_pick_path_ignores_stale_cached_active_round(self):
        self.start()
        rnd3 = self.fx.round(3)
        with patch.object(Draft, "active_round", new_callable=PropertyMock, return_value=rnd3):
            r = self.fx.pick(rnd3, rnd3.captain)
        self.assertEqual(r.status_code, 409)
        self.assertEqual((r.data["code"], r.data["active_pick_number"]), ("not_active_round", 1))

    def test_resuming_and_completed_reject_everyone(self):
        rnd = self.start()
        for state in (TeamDraftState.RESUMING, TeamDraftState.COMPLETED):
            self.fx.draft.state = state
            self.fx.draft.save()
            self.assertEqual(self.fx.pick(rnd, self.fx.staff).status_code, 409)

    def test_untimed_draft_keeps_legacy_any_round_rule(self):
        fx = TimedDraftFixture(timer_enabled=False, prefix="legacy")
        rnd5 = fx.round(5)
        with self.captureOnCommitCallbacks(execute=True):
            r = fx.pick(rnd5, rnd5.captain)
        self.assertEqual(r.status_code, 201, r.data)
        rnd5.refresh_from_db()
        self.assertIsNone(rnd5.completed_at)
        self.assertIsNone(rnd5.pick_duration_ms)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.DRAFTING)

    def test_broadcasts_are_deferred_to_commit(self):
        rnd = self.start()
        with patch("app.functions.tournament.broadcast_event") as mock_bc, patch("app.functions.teamdraft.broadcast_event") as mock_td:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.assertEqual(self.fx.pick(rnd, rnd.captain).status_code, 201)
                mock_bc.assert_not_called()
                mock_td.assert_not_called()
            for cb in callbacks:
                cb()
            mock_bc.assert_called_once()
            self.assertEqual(mock_td.call_count, 1)


class PickTimingTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(grace_time_ms=1000, reserve_time_ms=5000)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.rnd = self.fx.start(now=timezone.now() - timedelta(seconds=3))

    def test_pick_records_duration_and_debits_reserve_then_activates_next(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.fx.pick(self.rnd, self.rnd.captain)
        self.assertEqual(r.status_code, 201, r.data)
        self.rnd.refresh_from_db()
        self.assertGreaterEqual(self.rnd.pick_duration_ms, 3000)
        self.assertGreaterEqual(self.rnd.reserve_used_ms, 2000)
        self.assertIsNotNone(self.rnd.completed_at)
        team = Team.objects.get(pk=self.fx.team_of(self.rnd.captain).pk)
        self.assertLessEqual(team.draft_reserve_ms, 3000)
        nxt = self.fx.draft.active_round
        self.assertEqual(nxt.pick_number, 2)
        self.assertIsNotNone(nxt.started_at)
        self.assertEqual(nxt.grace_time_ms, 1000)
        self.assertTrue(self.fx.events("round_started").filter(payload__pick_number=2).exists())

    def test_client_picked_at_within_window_is_honoured(self):
        early = (self.rnd.started_at + timedelta(milliseconds=500)).isoformat()
        with patch("app.functions.tournament.timezone.now", return_value=self.rnd.started_at + timedelta(seconds=1)):
            with self.captureOnCommitCallbacks(execute=True):
                r = self.fx.pick(self.rnd, self.rnd.captain, client_picked_at=early)
        self.assertEqual(r.status_code, 201, r.data)
        self.rnd.refresh_from_db()
        self.assertEqual(self.rnd.pick_duration_ms, 500)
        self.assertEqual(self.rnd.reserve_used_ms, 0)

    def test_client_picked_at_in_future_or_stale_falls_back_to_server_time(self):
        for prefix, bad in (("ctf", timezone.now() + timedelta(seconds=5)), ("cts", timezone.now() - timedelta(seconds=10))):
            fx = TimedDraftFixture(grace_time_ms=1000, prefix=prefix)
            with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
                rnd = fx.start(now=timezone.now() - timedelta(seconds=2))
            with self.captureOnCommitCallbacks(execute=True):
                r = fx.pick(rnd, rnd.captain, client_picked_at=bad.isoformat())
            self.assertEqual(r.status_code, 201, r.data)
            rnd.refresh_from_db()
            self.assertGreaterEqual(rnd.pick_duration_ms, 2000)

    def test_staff_pick_during_pause_charges_only_time_before_pause(self):
        fx = TimedDraftFixture(prefix="sp")
        now = timezone.now()
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            rnd = fx.start(now=now - timedelta(seconds=5))
        fx.draft.state = TeamDraftState.PAUSED
        fx.draft.paused_at = now - timedelta(seconds=4)
        fx.draft.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.pick(rnd, fx.staff).status_code, 201)
        rnd.refresh_from_db()
        self.assertGreaterEqual(rnd.pick_duration_ms, 1000)
        self.assertLessEqual(rnd.pick_duration_ms, 1500)
        self.assertEqual(rnd.reserve_used_ms, 0)

    def test_last_pick_completes_draft(self):
        fx = TimedDraftFixture(num_teams=1, prefix="one")
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            fx.start()
        for n in range(1, 5):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(fx.pick(fx.draft.active_round, fx.staff).status_code, 201)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.COMPLETED)
        self.assertEqual(fx.events("draft_completed").count(), 1)
        self.assertIsNone(fx.draft.active_round)


class UndoTests(TestCase):
    def armed_fixture(self, **kw: object) -> TimedDraftFixture:
        fx = TimedDraftFixture(**kw)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            fx.start()
        return fx

    def test_undo_emits_pick_undone_before_round_started(self) -> None:
        fx = self.armed_fixture(prefix="order")
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(fx.draft.active_round, fx.staff)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            fx.undo(fx.staff)
        types = list(
            DraftEvent.objects.nocache().filter(draft=fx.draft).order_by("pk").values_list("event_type", flat=True)
        )
        self.assertEqual(types[-2:], ["pick_undone", "round_started"])

    def test_undo_on_pending_is_409(self) -> None:
        fx = TimedDraftFixture()
        r = fx.undo(fx.staff)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "no_picks_to_undo")

    def test_snake_undo_keeps_next_round_captain(self) -> None:
        fx = self.armed_fixture()
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(fx.draft.active_round, fx.staff)
        rnd2_captain = fx.round(2).captain_id
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            r = fx.undo(fx.staff)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(fx.round(2).captain_id, rnd2_captain)
        self.assertIsNone(fx.round(2).started_at)
        rnd1 = fx.round(1)
        self.assertIsNone(rnd1.choice)
        self.assertIsNone(rnd1.completed_at)
        self.assertIsNotNone(rnd1.started_at, "re-armed because the undone pick was timed")
        self.assertEqual(fx.events("round_started").filter(payload__pick_number=1).count(), 2)

    def test_untimed_undo_leaves_round_unarmed(self) -> None:
        fx = TimedDraftFixture(timer_enabled=False, prefix="untimed")
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(fx.round(1), fx.staff)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.undo(fx.staff).status_code, 200)
        self.assertIsNone(fx.round(1).started_at)
        self.assertFalse(fx.events("round_started").exists())

    def test_undo_last_pick_of_completed_timed_draft_restarts_clock(self) -> None:
        fx = self.armed_fixture(num_teams=1, prefix="done")
        for _ in range(4):
            with self.captureOnCommitCallbacks(execute=True):
                fx.pick(fx.draft.active_round, fx.staff)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.COMPLETED)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True) as mock_start, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.undo(fx.staff).status_code, 200)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.DRAFTING)
        self.assertTrue(fx.draft.clock_armed)
        mock_start.assert_called_once()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.pick(fx.draft.active_round, fx.draft.active_round.captain).status_code, 201)

    def test_undo_completed_untimed_draft_is_drafting_unarmed(self) -> None:
        fx = TimedDraftFixture(timer_enabled=False, num_teams=1, prefix="udone")
        for _ in range(4):
            with self.captureOnCommitCallbacks(execute=True):
                fx.pick(fx.draft.active_round, fx.staff)
        with self.captureOnCommitCallbacks(execute=True):
            fx.undo(fx.staff)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.DRAFTING)
        self.assertFalse(fx.draft.clock_armed)

    def test_undo_does_not_refund_reserve(self) -> None:
        fx = self.armed_fixture(grace_time_ms=1000)
        rnd = fx.draft.active_round
        rnd.started_at = timezone.now() - timedelta(seconds=4)
        rnd.save()
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(rnd, fx.staff)
        team = Team.objects.get(pk=fx.team_of(rnd.captain).pk)
        spent = team.draft_reserve_ms
        self.assertLess(spent, 30000)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            fx.undo(fx.staff)
        self.assertEqual(Team.objects.get(pk=team.pk).draft_reserve_ms, spent)

    def test_undo_during_resuming_keeps_clock_armed(self) -> None:
        fx = self.armed_fixture(prefix="ur")
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(fx.draft.active_round, fx.staff)
        fx.draft.state = TeamDraftState.RESUMING
        fx.draft.resuming_until = timezone.now() + timedelta(seconds=3)
        fx.draft.save()
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True) as mock_start, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.undo(fx.staff).status_code, 200)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.draft.state, TeamDraftState.RESUMING)
        rnd1 = fx.round(1)
        self.assertEqual(rnd1.started_at, fx.draft.resuming_until)
        self.assertIsNone(fx.round(2).started_at)
        self.assertTrue(fx.draft.clock_armed)
        mock_start.assert_called_once()

    def test_undo_during_pause_leaves_round_unarmed_until_resume(self) -> None:
        fx = self.armed_fixture(prefix="up")
        with self.captureOnCommitCallbacks(execute=True):
            fx.pick(fx.draft.active_round, fx.staff)
        fx.draft.state = TeamDraftState.PAUSED
        fx.draft.paused_at = timezone.now()
        fx.draft.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.undo(fx.staff).status_code, 200)
        rnd1 = fx.round(1)
        self.assertEqual((rnd1.started_at, rnd1.grace_time_ms), (None, 30000))
        self.assertEqual(fx.events("round_started").filter(payload__pick_number=1).count(), 1, "no new round_started while paused")
        client = APIClient()
        client.force_authenticate(fx.staff)
        with patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(client.post(f"/api/draft/{fx.draft.pk}/resume/", {}, format="json").status_code, 200)
        fx.draft.refresh_from_db()
        self.assertEqual(fx.round(1).started_at, fx.draft.resuming_until)
        self.assertTrue(fx.draft.clock_armed)

    def test_directly_built_untimed_pending_draft_undo_after_pick_is_200(self) -> None:
        fx = TimedDraftFixture(timer_enabled=False, prefix="direct")
        fx.draft.state = TeamDraftState.PENDING   # models a Draft whose rounds were created without build_rounds
        fx.draft.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.pick(fx.round(1), fx.staff).status_code, 201)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fx.undo(fx.staff).status_code, 200)
        self.assertIsNone(fx.round(1).choice)
