"""DraftOptions model, lazy creation, Draft state/clock_armed, migration state rule (spec §2)."""

import importlib
from datetime import date, timedelta
from unittest.mock import PropertyMock, patch

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.management.commands import sync_prod_tournaments
from app.serializers import DraftSerializerSlim, TournamentSerializer
from app.tests.teamdraft_fixtures import TimedDraftFixture
from app.models import (
    Draft,
    DraftOptions,
    DraftRound,
    Team,
    TeamDraftState,
    TimeoutAction,
    Tournament,
)

User = get_user_model()


def make_tournament(num_teams: int = 4, prefix: str = "do") -> Tournament:
    t = Tournament.objects.create(name=f"{prefix} tournament", date_played=date.today())
    users = [
        User.objects.create_user(username=f"{prefix}_u{i}", password="x")
        for i in range(num_teams * 5)
    ]
    t.users.set(users)
    for i in range(num_teams):
        team = Team.objects.create(
            tournament=t, name=f"T{i + 1}", captain=users[i * 5], draft_order=i + 1
        )
        team.members.add(users[i * 5])
    return t


class DraftOptionsModelTests(TestCase):
    def test_defaults(self):
        t = make_tournament(1)
        opts = DraftOptions.objects.create(tournament=t)
        self.assertFalse(opts.timer_enabled)
        self.assertEqual(opts.grace_time_ms, 30000)
        self.assertEqual(opts.reserve_time_ms, 30000)
        self.assertEqual(opts.timeout_action, TimeoutAction.SKIP_TURN)
        self.assertEqual(TimeoutAction.values, ["skip_turn"])

    def test_get_draft_options_creates_lazily_once(self):
        t = make_tournament(1)
        self.assertFalse(DraftOptions.objects.filter(tournament=t).exists())
        a = t.get_draft_options()
        b = t.get_draft_options()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(DraftOptions.objects.filter(tournament=t).count(), 1)

    def test_ensure_for_writes_only_provided_fields(self):
        t = make_tournament(1)
        DraftOptions.ensure_for(t, timer_enabled=True, grace_time_ms=5000)
        opts = DraftOptions.ensure_for(t, timer_enabled=False)
        self.assertFalse(opts.timer_enabled)
        self.assertEqual(opts.grace_time_ms, 5000)
        self.assertEqual(opts.reserve_time_ms, 30000)


class DraftStateTests(TestCase):
    def test_build_rounds_untimed_lands_in_drafting_unarmed(self):
        t = make_tournament()
        draft = Draft.objects.create(tournament=t, draft_style="snake")
        draft.build_rounds()
        draft.refresh_from_db()
        self.assertEqual(draft.state, TeamDraftState.DRAFTING)
        self.assertFalse(draft.clock_armed)
        self.assertIsNone(draft.active_round.started_at)
        self.assertEqual(draft.active_round.pick_number, 1)
        for team in t.teams.all():
            self.assertEqual(team.draft_reserve_ms, 30000)
            self.assertFalse(team.draft_is_ready)
            self.assertFalse(team.draft_has_connected)

    def test_build_rounds_timed_lands_in_pending_and_emits_lobby_opened(self):
        t = make_tournament()
        DraftOptions.ensure_for(t, timer_enabled=True, reserve_time_ms=12000)
        draft = Draft.objects.create(tournament=t, draft_style="shuffle")
        draft.build_rounds()
        draft.refresh_from_db()
        self.assertEqual(draft.state, TeamDraftState.PENDING)
        self.assertFalse(draft.clock_armed)
        ev = draft.events.filter(event_type="draft_lobby_opened").get()
        self.assertEqual(
            ev.payload,
            {"timer_enabled": True, "grace_time_ms": 30000, "reserve_time_ms": 12000},
        )
        self.assertEqual(t.teams.first().draft_reserve_ms, 12000)

    def test_build_rounds_resets_ready_and_connected_flags(self):
        t = make_tournament()
        draft = Draft.objects.create(tournament=t, draft_style="snake")
        draft.build_rounds()
        team = t.teams.first()
        team.draft_is_ready = team.draft_has_connected = True
        team.save()
        draft.build_rounds()
        team.refresh_from_db()
        self.assertFalse(team.draft_is_ready)
        self.assertFalse(team.draft_has_connected)

    def test_clock_armed_requires_timer_state_and_started_at(self):
        t = make_tournament()
        draft = Draft.objects.create(tournament=t, draft_style="snake")
        draft.build_rounds()
        rnd = draft.active_round
        rnd.started_at = timezone.now()
        rnd.save()
        self.assertFalse(draft.clock_armed, "timer disabled")
        DraftOptions.ensure_for(t, timer_enabled=True)
        self.assertTrue(draft.clock_armed)
        draft.state = TeamDraftState.PAUSED
        self.assertFalse(draft.clock_armed, "paused")
        draft.state = TeamDraftState.RESUMING
        self.assertTrue(draft.clock_armed, "resuming counts")

    def test_active_round_is_lowest_unpicked(self):
        t = make_tournament()
        draft = Draft.objects.create(tournament=t, draft_style="normal")
        draft.build_rounds()
        first = draft.draft_rounds.get(pick_number=1)
        first.choice = t.users.exclude(
            pk__in=t.teams.values_list("captain_id", flat=True)
        ).first()
        first.save()
        self.assertEqual(draft.active_round.pick_number, 2)
        DraftRound.objects.filter(draft=draft).update(choice=first.choice)
        self.assertIsNone(draft.active_round)

    def test_lock_active_round_ignores_cached_property(self):
        t = make_tournament()
        draft = Draft.objects.create(tournament=t, draft_style="snake")
        draft.build_rounds()
        with patch.object(
            Draft,
            "active_round",
            new_callable=PropertyMock,
            return_value=draft.draft_rounds.get(pick_number=3),
        ):
            with transaction.atomic():
                self.assertEqual(draft.lock_active_round().pick_number, 1)


class MigrationStateRuleTests(TestCase):
    def test_set_initial_draft_states(self):
        mod = importlib.import_module("app.migrations.0097_teamdraft_timer")
        t_empty = make_tournament(1, "m0")
        empty = Draft.objects.create(tournament=t_empty, draft_style="snake")
        t_half = make_tournament(2, "m1")
        half = Draft.objects.create(tournament=t_half, draft_style="snake")
        half.build_rounds()
        t_done = make_tournament(2, "m2")
        done = Draft.objects.create(tournament=t_done, draft_style="snake")
        done.build_rounds()
        DraftRound.objects.filter(draft=done).update(choice=t_done.users.first())
        Draft.objects.update(state="paused")

        mod.set_initial_draft_states(global_apps, None)

        self.assertEqual(Draft.objects.get(pk=empty.pk).state, "pending")
        self.assertEqual(Draft.objects.get(pk=half.pk).state, "drafting")
        self.assertEqual(Draft.objects.get(pk=done.pk).state, "completed")


class LegacyStateDerivationTests(TestCase):
    def test_derive_legacy_state(self):
        t = make_tournament(2, "dl")
        draft = Draft.objects.create(tournament=t, draft_style="snake")
        self.assertEqual(draft.derive_legacy_state(), TeamDraftState.PENDING)
        draft.build_rounds()
        self.assertEqual(draft.derive_legacy_state(), TeamDraftState.DRAFTING)
        DraftRound.objects.filter(draft=draft).update(choice=t.users.first())
        self.assertEqual(draft.derive_legacy_state(), TeamDraftState.COMPLETED)

    def _sync_rounds(self, t: Tournament, picked: bool) -> list[dict]:
        captains = [team.captain for team in t.teams.order_by("draft_order")]
        players = list(t.users.exclude(pk__in=[c.pk for c in captains]))
        return [
            {
                "captain": {"username": captains[i % 2].username},
                "choice": {"username": players[i].username} if picked else None,
                "pick_number": i + 1,
                "pick_phase": i // 2 + 1,
            }
            for i in range(4)
        ]

    def test_sync_create_draft_derives_state(self):
        for prefix, picked, expected in (("sc", True, "completed"), ("sd", False, "drafting")):
            t = make_tournament(2, prefix)
            cmd = sync_prod_tournaments.Command()
            cmd.user_map = {f"username:{u.username}": u for u in t.users.all()}
            draft = cmd._create_draft(
                t, {"draft_style": "snake", "draft_rounds": self._sync_rounds(t, picked)}, {}
            )
            self.assertEqual(Draft.objects.get(pk=draft.pk).state, expected, prefix)
        t = make_tournament(1, "se")
        cmd = sync_prod_tournaments.Command()
        draft = cmd._create_draft(t, {"draft_style": "snake", "draft_rounds": []}, {})
        self.assertEqual(Draft.objects.get(pk=draft.pk).state, "pending")


class SerializerFieldTests(TestCase):
    def test_slim_draft_carries_timer_fields(self):
        fx = TimedDraftFixture()
        data = DraftSerializerSlim(fx.draft).data
        for key in ("state", "clock_armed", "paused_at", "resuming_until", "is_manual_pause", "draft_options"):
            self.assertIn(key, data)
        self.assertEqual(data["state"], "pending")
        self.assertFalse(data["clock_armed"])
        self.assertEqual(data["draft_options"]["reserve_time_ms"], 30000)
        rnd = data["draft_rounds"][0]
        for key in ("started_at", "timed_out_at", "pick_duration_ms", "reserve_used_ms", "skip_count"):
            self.assertIn(key, rnd)
        team = data["tournament"]["teams"][0]
        for key in ("draft_reserve_ms", "draft_is_ready", "draft_is_connected"):
            self.assertIn(key, team)

    def test_tournament_serializer_exposes_options_lazily(self):
        t = make_tournament(1, "ser")
        t.refresh_from_db()
        data = TournamentSerializer(t).data
        self.assertEqual(data["draft_options"]["timer_enabled"], False)
        self.assertTrue(DraftOptions.objects.filter(tournament=t).exists())


class SettingsWriteTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture()
        self.client = APIClient()
        self.client.force_authenticate(self.fx.staff)
        self.url = f"/api/tournaments/{self.fx.tournament.pk}/"

    def test_staff_patch_writes_options_and_reseeds_pending_pools(self):
        r = self.client.patch(self.url, {"draft_options": {"reserve_time_ms": 15000, "grace_time_ms": 10000}}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["draft_options"]["reserve_time_ms"], 15000)
        self.assertEqual(Team.objects.get(pk=self.fx.teams[0].pk).draft_reserve_ms, 15000)

    def test_non_staff_patch_is_forbidden(self):
        self.client.force_authenticate(self.fx.captains[0])
        r = self.client.patch(self.url, {"draft_options": {"timer_enabled": False}}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_invalid_values_are_rejected_without_write(self):
        r = self.client.patch(self.url, {"draft_options": {"grace_time_ms": 0}}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(self.url, {"draft_options": {"reserve_time_ms": -1}}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(DraftOptions.objects.get(pk=self.fx.options.pk).grace_time_ms, 30000)

    def test_timeout_action_is_read_only(self):
        r = self.client.patch(self.url, {"draft_options": {"timeout_action": "other"}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["draft_options"]["timeout_action"], "skip_turn")

    def test_mid_draft_change_does_not_touch_active_round_or_reserve(self):
        with self.captureOnCommitCallbacks(execute=True):
            rnd = self.fx.start()
        self.client.patch(self.url, {"draft_options": {"grace_time_ms": 5000, "reserve_time_ms": 1000}}, format="json")
        rnd.refresh_from_db()
        self.assertEqual(rnd.grace_time_ms, 30000)
        self.assertEqual(Team.objects.get(pk=self.fx.team_of(rnd.captain).pk).draft_reserve_ms, 30000)

    def _disable_and_assert_drafting_unarmed(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.patch(self.url, {"draft_options": {"timer_enabled": False}}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.fx.draft.refresh_from_db()
        self.assertEqual(self.fx.draft.state, TeamDraftState.DRAFTING)
        self.assertFalse(self.fx.draft.clock_armed)
        self.assertIsNone(self.fx.draft.paused_at)
        self.assertIsNone(self.fx.draft.active_round.started_at)
        self.assertEqual(self.fx.pick(self.fx.draft.active_round, self.fx.draft.active_round.captain).status_code, 201)

    def test_timer_off_from_pending(self):
        self._disable_and_assert_drafting_unarmed()
        self.assertFalse(self.fx.events("draft_resumed").exists())

    def test_timer_off_from_drafting_armed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.start()
        self._disable_and_assert_drafting_unarmed()

    def test_timer_off_from_paused_emits_draft_resumed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.start()
        self.fx.draft.state = TeamDraftState.PAUSED
        self.fx.draft.paused_at = timezone.now()
        self.fx.draft.is_manual_pause = True
        self.fx.draft.save()
        self._disable_and_assert_drafting_unarmed()
        self.assertEqual(self.fx.events("draft_resumed").count(), 1)
        self.fx.draft.refresh_from_db()
        self.assertFalse(self.fx.draft.is_manual_pause)

    def test_timer_off_from_resuming_emits_draft_resumed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.fx.start()
        self.fx.draft.state = TeamDraftState.RESUMING
        self.fx.draft.resuming_until = timezone.now() + timedelta(seconds=3)
        self.fx.draft.save()
        self._disable_and_assert_drafting_unarmed()
        self.assertEqual(self.fx.events("draft_resumed").count(), 1)
        self.fx.draft.refresh_from_db()
        self.assertIsNone(self.fx.draft.resuming_until)
