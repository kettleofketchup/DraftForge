"""Hero draft turn timer driven by the tournament's DraftOptions hero_* fields."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Game, Team, Tournament
from draft.models import DraftOptions, DraftTeam, HeroDraft, HeroDraftRound
from draft.serializers.hero import HeroDraftSerializer
from draft.services.hero import (
    build_draft_rounds,
    new_herodraft_for_game,
    submit_pick,
)
from draft.tasks.hero_tick import broadcast_tick, check_timeout
from draft.tests.team_fixtures import TimedDraftFixture


def make_game(prefix: str) -> Game:
    tournament = Tournament.objects.create(
        name=f"{prefix} tournament", date_played=date.today()
    )
    captains = [
        CustomUser.objects.create_user(username=f"{prefix}_cap{i}", password="x")
        for i in range(2)
    ]
    teams = [
        Team.objects.create(tournament=tournament, name=f"{prefix} T{i}", captain=c)
        for i, c in enumerate(captains)
    ]
    return Game.objects.create(
        tournament=tournament, radiant_team=teams[0], dire_team=teams[1]
    )


def set_hero_options(game: Game, **fields: object) -> DraftOptions:
    options = game.tournament.get_draft_options(fresh=True)
    for key, value in fields.items():
        setattr(options, key, value)
    options.save()
    return options


def start_drafting(draft: HeroDraft) -> HeroDraftRound:
    first, second = list(draft.draft_teams.order_by("id"))
    first.is_first_pick = True
    first.save()
    second.is_first_pick = False
    second.save()
    build_draft_rounds(draft, first, second)
    draft.state = "drafting"
    draft.save()
    rnd = draft.rounds.order_by("round_number").first()
    rnd.state = "active"
    rnd.started_at = timezone.now()
    rnd.save()
    return rnd


class HeroDraftOptionsSnapshotTests(TestCase):
    def test_defaults_match_previous_hard_coded_values(self) -> None:
        game = make_game("def")
        draft = new_herodraft_for_game(game)
        self.assertTrue(draft.timer_enabled)
        self.assertEqual(
            {t.reserve_time_remaining for t in draft.draft_teams.all()}, {90000}
        )
        start_drafting(draft)
        self.assertEqual(
            set(draft.rounds.values_list("grace_time_ms", flat=True)), {30000}
        )

    def test_new_draft_picks_up_hero_options(self) -> None:
        game = make_game("opt")
        set_hero_options(
            game,
            hero_timer_enabled=False,
            hero_grace_time_ms=12000,
            hero_reserve_time_ms=45000,
        )
        draft = new_herodraft_for_game(game)
        self.assertFalse(draft.timer_enabled)
        self.assertEqual(
            {t.reserve_time_remaining for t in draft.draft_teams.all()}, {45000}
        )
        start_drafting(draft)
        self.assertEqual(draft.rounds.count(), 24)
        self.assertEqual(
            set(draft.rounds.values_list("grace_time_ms", flat=True)), {12000}
        )
        self.assertFalse(HeroDraftSerializer(draft).data["timer_enabled"])

    def test_changing_options_does_not_flip_live_draft(self) -> None:
        game = make_game("live")
        draft = new_herodraft_for_game(game)
        set_hero_options(game, hero_timer_enabled=False)
        draft.refresh_from_db()
        self.assertTrue(draft.timer_enabled)

    def test_grace_is_fixed_at_creation_not_roll(self) -> None:
        game = make_game("roll")
        set_hero_options(game, hero_grace_time_ms=12000)
        draft = new_herodraft_for_game(game)
        set_hero_options(game, hero_grace_time_ms=50000)
        draft.refresh_from_db()
        start_drafting(draft)
        self.assertEqual(
            set(draft.rounds.values_list("grace_time_ms", flat=True)), {12000}
        )

    def test_create_endpoint_uses_options(self) -> None:
        game = make_game("api")
        set_hero_options(game, hero_timer_enabled=False, hero_reserve_time_ms=60000)
        client = APIClient()
        client.force_authenticate(game.radiant_team.captain)
        r = client.post(f"/api/games/{game.id}/create-herodraft/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data["timer_enabled"])
        self.assertEqual(
            {t["reserve_time_remaining"] for t in r.data["draft_teams"]}, {60000}
        )

    def test_reset_restores_reserve_from_options(self) -> None:
        game = make_game("reset")
        set_hero_options(game, hero_reserve_time_ms=20000)
        draft = new_herodraft_for_game(game)
        DraftTeam.objects.filter(draft=draft).update(reserve_time_remaining=1)
        staff = CustomUser.objects.create_user(
            username="reset_staff", password="x", is_staff=True
        )
        client = APIClient()
        client.force_authenticate(staff)
        r = client.post(f"/api/herodraft/{draft.pk}/reset/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(
            set(draft.draft_teams.values_list("reserve_time_remaining", flat=True)),
            {20000},
        )

    def test_reset_resnapshots_all_timer_options(self) -> None:
        game = make_game("resnap")
        draft = new_herodraft_for_game(game)
        set_hero_options(
            game,
            hero_timer_enabled=False,
            hero_grace_time_ms=8000,
            hero_reserve_time_ms=15000,
        )
        staff = CustomUser.objects.create_user(
            username="resnap_staff", password="x", is_staff=True
        )
        client = APIClient()
        client.force_authenticate(staff)
        r = client.post(f"/api/herodraft/{draft.pk}/reset/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["timer_enabled"])
        draft.refresh_from_db()
        self.assertEqual(draft.grace_time_ms, 8000)
        self.assertEqual(
            set(draft.draft_teams.values_list("reserve_time_remaining", flat=True)),
            {15000},
        )

    def test_untimed_pick_does_not_consume_reserve(self) -> None:
        game = make_game("pick")
        set_hero_options(game, hero_timer_enabled=False)
        draft = new_herodraft_for_game(game)
        rnd = start_drafting(draft)
        rnd.started_at = timezone.now() - timedelta(minutes=10)
        rnd.save()
        submit_pick(draft, rnd.draft_team, 1)
        team = DraftTeam.objects.get(pk=rnd.draft_team_id)
        self.assertEqual(team.reserve_time_remaining, 90000)

    def test_timed_pick_honours_fresh_client_picked_at(self) -> None:
        game = make_game("clientpick")
        set_hero_options(game, hero_timer_enabled=True)
        draft = new_herodraft_for_game(game)
        rnd = start_drafting(draft)
        now = timezone.now()
        rnd.started_at = now - timedelta(milliseconds=rnd.grace_time_ms + 1900)
        rnd.save()
        reserve_before = DraftTeam.objects.get(
            pk=rnd.draft_team_id
        ).reserve_time_remaining
        submit_pick(
            draft, rnd.draft_team, 1, client_picked_at=now - timedelta(seconds=1)
        )
        team = DraftTeam.objects.get(pk=rnd.draft_team_id)
        self.assertEqual(team.reserve_time_remaining, reserve_before)


class HeroDraftUntimedTickTests(TransactionTestCase):
    def setUp(self) -> None:
        self.game = make_game("tick")

    def _drafting(self, timer_enabled: bool) -> tuple[HeroDraft, HeroDraftRound]:
        set_hero_options(self.game, hero_timer_enabled=timer_enabled)
        draft = new_herodraft_for_game(self.game)
        rnd = start_drafting(draft)
        rnd.started_at = timezone.now() - timedelta(minutes=10)
        rnd.save()
        return draft, rnd

    def test_timer_disabled_never_auto_picks(self) -> None:
        draft, rnd = self._drafting(timer_enabled=False)
        self.assertIsNone(async_to_sync(check_timeout)(draft.id))
        rnd.refresh_from_db()
        self.assertEqual(rnd.state, "active")
        self.assertIsNone(rnd.hero_id)

    def test_timer_enabled_still_auto_picks(self) -> None:
        draft, rnd = self._drafting(timer_enabled=True)
        self.assertIsNotNone(async_to_sync(check_timeout)(draft.id))
        rnd.refresh_from_db()
        self.assertEqual(rnd.state, "completed")

    @patch("draft.tasks.hero_tick.get_channel_layer")
    def test_tick_carries_timer_enabled(
        self, mock_get_channel_layer: MagicMock
    ) -> None:
        layer = MagicMock()
        layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = layer
        draft, _ = self._drafting(timer_enabled=False)
        async_to_sync(broadcast_tick)(draft.id)
        message = layer.group_send.call_args[0][1]
        self.assertIs(message["timer_enabled"], False)


class HeroDraftOptionsApiTests(TestCase):
    def setUp(self) -> None:
        self.fx = TimedDraftFixture()
        self.client = APIClient()
        self.client.force_authenticate(self.fx.staff)
        self.url = f"/api/tournaments/{self.fx.tournament.pk}/"

    def test_round_trip_hero_options(self) -> None:
        r = self.client.patch(
            self.url,
            {
                "draft_options": {
                    "hero_timer_enabled": False,
                    "hero_grace_time_ms": 15000,
                    "hero_reserve_time_ms": 60000,
                }
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["draft_options"]["hero_timer_enabled"])
        self.assertEqual(r.data["draft_options"]["hero_grace_time_ms"], 15000)
        self.assertEqual(r.data["draft_options"]["hero_reserve_time_ms"], 60000)
        opts = DraftOptions.objects.get(tournament=self.fx.tournament)
        self.assertFalse(opts.hero_timer_enabled)
        self.assertEqual(opts.hero_grace_time_ms, 15000)
        self.assertEqual(opts.hero_reserve_time_ms, 60000)
        self.assertFalse(self.fx.events("draft_options_changed").exists())
        r = self.client.get(self.url)
        self.assertEqual(r.data["draft_options"]["hero_reserve_time_ms"], 60000)

    def test_invalid_hero_values_rejected_without_write(self) -> None:
        for payload in ({"hero_grace_time_ms": 0}, {"hero_reserve_time_ms": -1}):
            r = self.client.patch(self.url, {"draft_options": payload}, format="json")
            self.assertEqual(r.status_code, 400, payload)
        opts = DraftOptions.objects.get(tournament=self.fx.tournament)
        self.assertEqual(opts.hero_grace_time_ms, 30000)
        self.assertEqual(opts.hero_reserve_time_ms, 90000)
