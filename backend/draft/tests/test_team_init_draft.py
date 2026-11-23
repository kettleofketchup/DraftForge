"""Draft init and restart reset teams in place without destroying them."""

from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.serializers import users_remaining_pks
from bracket.models import BracketSlot, TournamentBracket
from draft.models import Draft, DraftEvent, DraftOptions, DraftTeam, HeroDraft
from draft.services.team_reset import reset_draft_teams
from league.models import League, LeagueUser
from org.models import Organization
from tests.populate.utils import ensure_org_user
from tournament.state import tournament_state_queryset
from user.tests.test_cacheops_integration import _redis_reachable


class TeamResetFixture:
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Reset Org")
        self.league = League.objects.create(
            organization=self.org, name="Reset League", steam_league_id=91001
        )
        self.tournament = Tournament.objects.create(
            name="Reset Cup", date_played=timezone.now(), league=self.league
        )
        self.x = self.make_user("reset_x")
        self.y = self.make_user("reset_y")
        self.z = self.make_user("reset_z")
        self.tournament.users.add(self.x, self.y, self.z)
        self.team = Team.objects.create(
            tournament=self.tournament, name="Resetters", draft_order=3
        )

    def make_user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="test")
        ensure_org_user(user, self.org, mmr=3000)
        return user

    def corrupt_captain(self) -> None:
        self.team.members.set([self.x, self.y])
        self.team.captain = self.z
        self.team.save()

    def member_pks(self, team: Team) -> list[int]:
        return list(Team.objects.get(pk=team.pk).members.values_list("pk", flat=True))


class TeamResetTests(TeamResetFixture, TestCase):
    def test_reset_captain_not_member_keeps_team_and_game(self) -> None:
        self.corrupt_captain()
        game = Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        removed = self.team.reset_to_captain()

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        self.assertEqual(self.member_pks(self.team), [self.z.pk])
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertEqual({u.pk for u in removed}, {self.x.pk, self.y.pk})

    def test_reset_clears_draft_state(self) -> None:
        self.team.members.set([self.x, self.y])
        self.team.captain = self.x
        self.team.deputy_captain = self.y
        self.team.dropin_members.add(self.z)
        self.team.left_members.add(self.y)
        captain_lu = LeagueUser.objects.get(user=self.x, league=self.league)
        other_lu = LeagueUser.objects.get(user=self.y, league=self.league)
        self.team.league_users.set([captain_lu, other_lu])
        self.team.current_points = 9
        self.team.placement = 2
        self.team.draft_reserve_ms = 1234
        self.team.draft_is_ready = True
        self.team.draft_is_connected = True
        self.team.draft_has_connected = True
        self.team.save()

        self.team.reset_to_captain()

        team = Team.objects.get(pk=self.team.pk)
        self.assertEqual(list(team.members.values_list("pk", flat=True)), [self.x.pk])
        self.assertEqual(team.dropin_members.count(), 0)
        self.assertEqual(team.left_members.count(), 0)
        self.assertEqual(
            list(team.league_users.values_list("pk", flat=True)), [captain_lu.pk]
        )
        self.assertIsNone(team.deputy_captain)
        self.assertIsNone(team.draft_reserve_ms)
        self.assertFalse(team.draft_is_ready)
        self.assertFalse(team.draft_is_connected)
        self.assertFalse(team.draft_has_connected)
        self.assertEqual(team.current_points, 0)
        self.assertIsNone(team.placement)
        self.assertEqual(team.name, "Resetters")
        self.assertEqual(team.draft_order, 3)

    def test_dropin_and_left_clear_does_not_delete_team(self) -> None:
        self.team.members.set([self.x])
        self.team.captain = self.x
        self.team.save()
        self.team.dropin_members.add(self.y)
        self.team.left_members.add(self.z)

        self.team.dropin_members.clear()
        self.team.left_members.clear()

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_rebuild_teams_clear_only_with_non_member_captain(self) -> None:
        self.corrupt_captain()
        game = Game.objects.create(tournament=self.tournament, dire_team=self.team)
        draft = Draft.objects.create(tournament=self.tournament)

        draft.rebuild_teams(clear_only=True)

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        self.assertEqual(self.member_pks(self.team), [self.z.pk])
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())

    def test_reset_drops_audited_ineligible_team(self) -> None:
        self.team.members.set([self.x])
        self.team.captain = self.x
        self.team.save()
        outsider = self.make_user("reset_outsider")
        audited = Team.objects.create(
            tournament=self.tournament, name="Audited", captain=outsider
        )
        audited.members.add(outsider)
        log = TeamLog.objects.create(
            team=audited,
            team_snapshot_id=audited.pk,
            team_name=audited.name,
            via=TeamLogVia.WEB,
            action=TeamLogAction.RENAME,
        )

        report = reset_draft_teams(self.tournament, force=False)

        self.assertFalse(Team.objects.filter(pk=audited.pk).exists())
        self.assertEqual([entry["pk"] for entry in report.dropped_teams], [audited.pk])
        log.refresh_from_db()
        self.assertIsNone(log.team)


class TeamResetCacheTests(TeamResetFixture, TransactionTestCase):
    def test_reset_visible_through_cache(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        self.team.members.set([self.x, self.y])
        self.team.captain = self.x
        self.team.save()
        warm = Team.objects.cache().get(pk=self.team.pk)
        self.assertEqual(
            sorted(warm.members.cache().values_list("pk", flat=True)),
            sorted([self.x.pk, self.y.pk]),
        )

        self.team.reset_to_captain()

        cached = Team.objects.cache().get(pk=self.team.pk)
        self.assertEqual(
            list(cached.members.cache().values_list("pk", flat=True)), [self.x.pk]
        )


class DraftEligibilityCacheTests(TeamResetFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        self.draft = Draft.objects.create(tournament=self.tournament)

    def remaining_pks(self) -> set[int]:
        draft = Draft.objects.get(pk=self.draft.pk)
        return set(draft.users_remaining.values_list("pk", flat=True))

    def team_pks(self) -> set[int]:
        draft = Draft.objects.get(pk=self.draft.pk)
        return set(draft.teams.values_list("pk", flat=True))

    def test_users_remaining_drops_player_added_to_kept_team(self) -> None:
        self.assertEqual(self.remaining_pks(), {self.x.pk, self.y.pk, self.z.pk})

        self.team.members.add(self.x)

        self.assertEqual(self.remaining_pks(), {self.y.pk, self.z.pk})

    def test_teams_include_team_once_captain_joins_pool(self) -> None:
        captain = self.make_user("reset_n")
        other = Team.objects.create(
            tournament=self.tournament, name="Newcomers", captain=captain
        )
        other.members.add(captain)
        self.assertEqual(self.team_pks(), set())

        self.tournament.users.add(captain)

        self.assertEqual(self.team_pks(), {other.pk})


INIT_DRAFT_URL = "/api/tournaments/init-draft"
REBUILD_URL = "/api/tournaments/draft-rebuild"


class InitDraftEndpointTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Init Org")
        self.league = League.objects.create(
            organization=self.org, name="Init League", steam_league_id=91002
        )
        self.tournament = Tournament.objects.create(
            name="Init Cup", date_played=timezone.now(), league=self.league
        )
        DraftOptions.ensure_for(self.tournament, timer_enabled=False)
        self.admin = CustomUser.objects.create_user(
            username="init_admin", password="test", is_staff=True, is_superuser=True
        )
        self.cap_a = self.make_user("init_cap_a", 3000)
        self.cap_b = self.make_user("init_cap_b", 4000)
        self.p1 = self.make_user("init_p1", 2000)
        self.p2 = self.make_user("init_p2", 2500)
        self.tournament.users.add(self.cap_a, self.cap_b, self.p1, self.p2)
        self.team_a = self.make_team("Team A", self.cap_a, [self.p1], order=1)
        self.team_b = self.make_team("Team B", self.cap_b, [self.p2], order=2)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def make_user(self, username: str, mmr: int) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="test")
        ensure_org_user(user, self.org, mmr=mmr)
        return user

    def make_team(
        self,
        name: str,
        captain: CustomUser | None,
        others: list[CustomUser],
        order: int = 0,
    ) -> Team:
        team = Team.objects.create(
            tournament=self.tournament, name=name, captain=captain, draft_order=order
        )
        if captain:
            team.members.add(captain)
        if others:
            team.members.add(*others)
        return team

    def post(self, path: str = INIT_DRAFT_URL, **data: object) -> object:
        return self.client.post(
            path, {"tournament_pk": self.tournament.pk, **data}, format="json"
        )

    def team_snapshot(self) -> dict[int, list[int]]:
        return {
            team.pk: sorted(team.members.values_list("pk", flat=True))
            for team in Team.objects.filter(tournament=self.tournament)
        }

    def make_herodraft(self, team: Team) -> HeroDraft:
        game = Game.objects.create(tournament=self.tournament)
        herodraft = HeroDraft.objects.create(game=game)
        DraftTeam.objects.create(draft=herodraft, tournament_team=team)
        return herodraft

    def test_no_eligible_captains_400_nothing_changed(self) -> None:
        Team.objects.filter(tournament=self.tournament).update(captain=None)
        before = self.team_snapshot()

        resp = self.post()

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.team_snapshot(), before)

    def test_game_reference_409_without_force(self) -> None:
        Game.objects.create(
            tournament=self.tournament, radiant_team=self.team_a, dire_team=self.team_b
        )
        before = self.team_snapshot()

        resp = self.post()

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "draft_reset_has_references")
        self.assertEqual(
            resp.data["references"],
            {"app.Game.radiant_team": 1, "app.Game.dire_team": 1},
        )
        self.assertEqual(self.team_snapshot(), before)
        self.assertFalse(Draft.objects.filter(tournament=self.tournament).exists())

    def test_force_keeps_game_herodraft_bracketslot(self) -> None:
        game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team_a, dire_team=self.team_b
        )
        herodraft = self.make_herodraft(self.team_a)
        bracket = TournamentBracket.objects.create(tournament=self.tournament)
        slot = BracketSlot.objects.create(
            bracket=bracket, max_rounds=1, game=game, participant=self.team_b
        )

        resp = self.post(force=True)

        self.assertEqual(resp.status_code, 201)
        game.refresh_from_db()
        self.assertEqual(
            (game.radiant_team_id, game.dire_team_id),
            (self.team_a.pk, self.team_b.pk),
        )
        self.assertTrue(
            DraftTeam.objects.filter(
                draft=herodraft, tournament_team=self.team_a
            ).exists()
        )
        slot.refresh_from_db()
        self.assertEqual(slot.participant_id, self.team_b.pk)
        self.assertEqual(
            sorted(resp.data["draft_reset"]["reset_teams"]),
            sorted([self.team_a.pk, self.team_b.pk]),
        )

    def test_herodraft_only_reference_triggers_409(self) -> None:
        self.make_herodraft(self.team_b)

        resp = self.post()

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.data["references"], {"draft.DraftTeam.tournament_team": 1}
        )

    def test_ineligible_referenced_team_kept_unreferenced_deleted(self) -> None:
        outsider = self.make_user("init_outsider", 1000)
        kept = self.make_team("Kept", None, [outsider], order=3)
        dropped = self.make_team("Dropped", outsider, [], order=4)
        self.make_herodraft(kept)

        resp = self.post(force=True)

        self.assertEqual(resp.status_code, 201)
        report = resp.data["draft_reset"]
        self.assertTrue(Team.objects.filter(pk=kept.pk).exists())
        self.assertFalse(Team.objects.filter(pk=dropped.pk).exists())
        self.assertEqual(
            [(t["pk"], t["name"], t["reason"]) for t in report["kept_teams"]],
            [(kept.pk, "Kept", "no_captain")],
        )
        self.assertEqual(
            [(t["pk"], t["name"], t["reason"]) for t in report["dropped_teams"]],
            [(dropped.pk, "Dropped", "captain_not_in_pool")],
        )
        self.assertEqual(
            sorted(Team.objects.get(pk=kept.pk).members.values_list("pk", flat=True)),
            [outsider.pk],
        )
        draft = Draft.objects.get(tournament=self.tournament)
        self.assertEqual(
            set(draft.draft_rounds.values_list("captain_id", flat=True)),
            {self.cap_a.pk, self.cap_b.pk},
        )
        self.assertEqual(draft.draft_rounds.count(), 8)

    def test_kept_team_members_in_pool_are_not_draftable(self) -> None:
        p3 = self.make_user("init_p3", 1500)
        p4 = self.make_user("init_p4", 1800)
        self.tournament.users.add(p3, p4)
        kept = self.make_team("Kept", None, [p3], order=3)
        self.make_herodraft(kept)

        resp = self.post(force=True)

        self.assertEqual(resp.status_code, 201)
        draft = Draft.objects.get(tournament=self.tournament)
        remaining = set(draft.users_remaining.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.p1.pk, self.p2.pk, p4.pk})
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        self.assertNotIn(p3.pk, users_remaining_pks(state.draft))
        first = draft.draft_rounds.order_by("pick_number").first()
        with self.assertRaises(ValueError):
            first.pick_player(p3)
        self.assertEqual(
            list(p3.teams_as_member.values_list("pk", flat=True)), [kept.pk]
        )

    def test_rebuild_skips_kept_captainless_team(self) -> None:
        outsider = self.make_user("rebuild_outsider", 1000)
        self.tournament.users.add(self.make_user("rebuild_p3", 1500))
        kept = self.make_team("Kept", None, [outsider], order=3)
        foreign = self.make_team("Foreign", outsider, [], order=4)
        self.make_herodraft(kept)
        self.make_herodraft(foreign)

        resp = self.post(REBUILD_URL)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            list(Team.objects.get(pk=kept.pk).members.values_list("pk", flat=True)),
            [outsider.pk],
        )
        self.assertEqual(
            list(Team.objects.get(pk=foreign.pk).members.values_list("pk", flat=True)),
            [outsider.pk],
        )
        draft = Draft.objects.get(tournament=self.tournament)
        self.assertEqual(
            set(draft.draft_rounds.values_list("captain_id", flat=True)),
            {self.cap_a.pk, self.cap_b.pk},
        )
        self.assertEqual(draft.draft_rounds.count(), 8)

    def test_draft_teams_are_the_eligible_teams(self) -> None:
        outsider = self.make_user("teams_outsider", 1000)
        self.make_team("Kept", None, [outsider], order=0)
        draft = Draft.objects.create(tournament=self.tournament)

        self.assertEqual(
            set(draft.teams.values_list("pk", flat=True)),
            {self.team_a.pk, self.team_b.pk},
        )
        self.assertEqual(
            set(draft._simulate_draft("snake")), {self.team_a.pk, self.team_b.pk}
        )
        self.assertEqual(draft.snake_first_pick_mmr, 3000 + 2500)

    def test_reset_logs_removed_count(self) -> None:
        with patch("draft.views.team_setup.log") as log:
            resp = self.post()

        self.assertEqual(resp.status_code, 201)
        completed = [
            c for c in log.info.call_args_list if c.args[0] == "draft_reset_completed"
        ]
        self.assertEqual(completed[0].kwargs["removed_count"], 2)

    def test_restart_keeps_pks_and_resets(self) -> None:
        self.team_a.deputy_captain = self.p1
        self.team_a.current_points = 5
        self.team_a.placement = 1
        self.team_a.save()
        self.team_a.dropin_members.add(self.p2)

        resp = self.post()
        self.assertEqual(resp.status_code, 201)
        resp = self.post()

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            self.team_snapshot(),
            {self.team_a.pk: [self.cap_a.pk], self.team_b.pk: [self.cap_b.pk]},
        )
        team_a = Team.objects.get(pk=self.team_a.pk)
        self.assertIsNone(team_a.deputy_captain)
        self.assertEqual(team_a.dropin_members.count(), 0)
        self.assertEqual(team_a.current_points, 0)
        self.assertIsNone(team_a.placement)
        self.assertEqual(team_a.name, "Team A")

    def test_cleared_deputies_reported(self) -> None:
        self.team_a.deputy_captain = self.p1
        self.team_a.save()

        resp = self.post()

        self.assertEqual(
            resp.data["draft_reset"]["cleared_deputies"],
            [{"team": self.team_a.pk, "user": self.p1.pk}],
        )

    def test_side_effects_after_commit_only(self) -> None:
        self.tournament.discord_send_draft_link = True
        self.tournament.save()
        DraftOptions.ensure_for(self.tournament, timer_enabled=True)
        Draft.objects.create(tournament=self.tournament, draft_style="shuffle")
        order = MagicMock()
        with (
            patch("draft.views.team_setup.notify_draft_started") as notify,
            patch("app.cache_utils.invalidate_obj") as invalidate,
            patch("draft.services.team_broadcast.broadcast_event") as broadcast,
        ):
            order.attach_mock(invalidate, "invalidate")
            order.attach_mock(broadcast, "broadcast")
            order.attach_mock(notify, "notify")
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                resp = self.post()
            self.assertEqual(resp.status_code, 201)
            notify.assert_not_called()
            broadcast.assert_not_called()
            invalidate.assert_not_called()
            for callback in callbacks:
                callback()

        notify.assert_called_once()
        event_types = [c.args[0].event_type for c in broadcast.call_args_list]
        self.assertIn("draft_started", event_types)
        self.assertIn("draft_lobby_opened", event_types)
        names = [
            name
            for name, args, _ in order.mock_calls
            if name in ("broadcast", "notify")
            or (name == "invalidate" and isinstance(args[0], Tournament | Draft))
        ]
        self.assertIn("invalidate", names)
        first_invalidate = names.index("invalidate")
        self.assertLess(first_invalidate, names.index("broadcast"))
        self.assertLess(first_invalidate, names.index("notify"))

    def test_no_side_effects_when_build_rounds_raises(self) -> None:
        self.tournament.discord_send_draft_link = True
        self.tournament.save()
        client = APIClient(raise_request_exception=True)
        client.force_authenticate(user=self.admin)
        with (
            patch("draft.views.team_setup.notify_draft_started") as notify,
            patch.object(Draft, "build_rounds", side_effect=RuntimeError("boom")),
            self.captureOnCommitCallbacks(execute=False) as callbacks,
        ):
            with self.assertRaises(RuntimeError):
                client.post(
                    INIT_DRAFT_URL,
                    {"tournament_pk": self.tournament.pk},
                    format="json",
                )

        self.assertEqual(callbacks, [])
        notify.assert_not_called()
        self.assertEqual(
            self.team_snapshot(),
            {
                self.team_a.pk: sorted([self.cap_a.pk, self.p1.pk]),
                self.team_b.pk: sorted([self.cap_b.pk, self.p2.pk]),
            },
        )

    def test_select_for_update_and_atomic(self) -> None:
        manager = Tournament.objects
        real_select_for_update = manager.select_for_update
        depth_outside = len(connection.atomic_blocks)
        depths: list[int] = []

        def record_depth(*args: object, **kwargs: object) -> None:
            depths.append(len(connection.atomic_blocks))

        with (
            patch.object(
                manager, "select_for_update", side_effect=real_select_for_update
            ) as select_for_update,
            patch.object(Draft, "build_rounds", side_effect=record_depth),
        ):
            resp = self.post()

        self.assertEqual(resp.status_code, 201)
        select_for_update.assert_called()
        self.assertEqual(len(depths), 1)
        self.assertGreater(depths[0], depth_outside)

    def test_rebuild_team_atomic_with_non_member_captain(self) -> None:
        self.team_a.members.set([self.p1])
        self.team_a.captain = self.cap_a
        self.team_a.save()
        game = Game.objects.create(tournament=self.tournament, radiant_team=self.team_a)
        with patch("draft.views.team_setup.notify_draft_started") as notify:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                resp = self.post(REBUILD_URL)
            notify.assert_not_called()
            for callback in callbacks:
                callback()

        self.assertEqual(resp.status_code, 201)
        notify.assert_called_once()
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertEqual(
            list(
                Team.objects.get(pk=self.team_a.pk).members.values_list("pk", flat=True)
            ),
            [self.cap_a.pk],
        )

    def test_409_usage_counts_each_game_once(self) -> None:
        for _ in range(2):
            Game.objects.create(
                tournament=self.tournament,
                radiant_team=self.team_a,
                dire_team=self.team_b,
                winning_team=self.team_a,
            )

        resp = self.post()

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.data["usage"],
            [
                {
                    "model": "app.Game",
                    "label": "game",
                    "label_plural": "games",
                    "count": 2,
                    "teams": [
                        {"pk": self.team_a.pk, "name": "Team A"},
                        {"pk": self.team_b.pk, "name": "Team B"},
                    ],
                }
            ],
        )
        self.assertEqual(resp.data["references"]["app.Game.radiant_team"], 2)

    def test_409_usage_counts_herodraft_not_draft_teams(self) -> None:
        game = Game.objects.create(tournament=self.tournament)
        herodraft = HeroDraft.objects.create(game=game)
        DraftTeam.objects.create(draft=herodraft, tournament_team=self.team_a)
        DraftTeam.objects.create(draft=herodraft, tournament_team=self.team_b)

        resp = self.post()

        self.assertEqual(resp.status_code, 409)
        usage = {u["model"]: u for u in resp.data["usage"]}
        self.assertEqual(set(usage), {"draft.HeroDraft"})
        self.assertEqual(usage["draft.HeroDraft"]["count"], 1)
        self.assertEqual(usage["draft.HeroDraft"]["label"], "HeroDraft")
        self.assertEqual(
            [t["name"] for t in usage["draft.HeroDraft"]["teams"]], ["Team A", "Team B"]
        )

    def test_report_names_captain_and_kept_usage(self) -> None:
        outsider = self.make_user("init_named_outsider", 1000)
        kept = self.make_team("Kept", outsider, [], order=3)
        dropped = self.make_team("Dropped", None, [], order=4)
        Game.objects.create(tournament=self.tournament, radiant_team=kept)

        resp = self.post(force=True)

        self.assertEqual(resp.status_code, 201)
        report = resp.data["draft_reset"]
        [kept_entry] = report["kept_teams"]
        self.assertEqual(kept_entry["reason"], "captain_not_in_pool")
        self.assertEqual(kept_entry["captain"]["pk"], outsider.pk)
        self.assertEqual(kept_entry["captain"]["username"], "init_named_outsider")
        self.assertEqual(
            [(u["model"], u["count"]) for u in kept_entry["usage"]],
            [("app.Game", 1)],
        )
        [dropped_entry] = report["dropped_teams"]
        self.assertEqual(dropped_entry["pk"], dropped.pk)
        self.assertEqual(dropped_entry["reason"], "no_captain")
        self.assertIsNone(dropped_entry["captain"])
        self.assertEqual(
            report["reset_team_names"],
            [
                {"pk": self.team_a.pk, "name": "Team A"},
                {"pk": self.team_b.pk, "name": "Team B"},
            ],
        )

    def test_restart_without_timer_broadcasts_draft_started(self) -> None:
        self.assertEqual(self.post().status_code, 201)
        draft = Draft.objects.get(tournament=self.tournament)
        DraftEvent.objects.filter(draft=draft).delete()

        with patch("draft.services.team_broadcast.broadcast_event") as broadcast:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post()

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            list(
                DraftEvent.objects.filter(draft=draft).values_list(
                    "event_type", flat=True
                )
            ),
            ["draft_started"],
        )
        self.assertEqual(
            [c.args[0].event_type for c in broadcast.call_args_list],
            ["draft_started"],
        )
