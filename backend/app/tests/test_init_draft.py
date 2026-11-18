"""Draft init and restart reset teams in place without destroying them."""

from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Draft,
    DraftOptions,
    DraftTeam,
    Game,
    HeroDraft,
    League,
    Organization,
    Team,
    Tournament,
)
from app.services.team_references import all_reference_keys, team_references
from bracket.models import BracketSlot, TournamentBracket
from league.models import LeagueUser
from org.models import OrgUser
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
        OrgUser.objects.create(user=user, organization=self.org, mmr=3000)
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

    def test_team_references_relation_names(self) -> None:
        expected = {
            "app.Game.radiant_team",
            "app.Game.dire_team",
            "app.Game.winning_team",
            "app.DraftTeam.tournament_team",
            "app.Tournament.winning_team",
            "bracket.BracketSlot.participant",
            "lobby.GameLobby.radiant_team",
            "lobby.GameLobby.dire_team",
            "lobby.GameLobby.provisional_winner_team",
        }
        keys = all_reference_keys()
        self.assertTrue(expected <= set(keys), expected - set(keys))
        self.assertFalse([k for k in keys if "_members." in k or "_league_users" in k])

    def test_team_references_counts_only_nonzero(self) -> None:
        self.team.members.set([self.x])
        self.team.captain = self.x
        self.team.save()
        other = Team.objects.create(tournament=self.tournament, name="Other")
        Game.objects.create(
            tournament=self.tournament, radiant_team=self.team, dire_team=other
        )
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        refs = team_references(Team.objects.filter(pk=self.team.pk))

        self.assertEqual(refs, {"app.Game.radiant_team": 2})
        self.assertEqual(team_references(Team.objects.none()), {})


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
        OrgUser.objects.create(user=user, organization=self.org, mmr=mmr)
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
        self.assertEqual(resp.data["references"], {"app.DraftTeam.tournament_team": 1})

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
            report["kept_teams"],
            [{"pk": kept.pk, "name": "Kept", "reason": "no_captain"}],
        )
        self.assertEqual(
            report["dropped_teams"],
            [{"pk": dropped.pk, "name": "Dropped", "reason": "captain_not_in_pool"}],
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
            patch("app.functions.tournament.notify_draft_started") as notify,
            patch("app.functions.tournament.invalidate_after_commit") as invalidate,
            patch("app.broadcast.broadcast_event") as broadcast,
        ):
            order.attach_mock(invalidate, "invalidate")
            order.attach_mock(broadcast, "broadcast")
            order.attach_mock(notify, "notify")
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                resp = self.post()
            self.assertEqual(resp.status_code, 201)
            notify.assert_not_called()
            broadcast.assert_not_called()
            invalidate.assert_called_once()
            for callback in callbacks:
                callback()

        notify.assert_called_once()
        event_types = [c.args[0].event_type for c in broadcast.call_args_list]
        self.assertIn("draft_started", event_types)
        self.assertIn("draft_lobby_opened", event_types)
        names = [
            c[0]
            for c in order.mock_calls
            if c[0] in ("invalidate", "broadcast", "notify")
        ]
        self.assertEqual(names[0], "invalidate")

    def test_no_side_effects_when_build_rounds_raises(self) -> None:
        self.tournament.discord_send_draft_link = True
        self.tournament.save()
        client = APIClient(raise_request_exception=True)
        client.force_authenticate(user=self.admin)
        with (
            patch("app.functions.tournament.notify_draft_started") as notify,
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
        seen: list[bool] = []

        def record_atomic(*args: object, **kwargs: object) -> None:
            seen.append(connection.in_atomic_block)

        with (
            patch.object(
                manager, "select_for_update", side_effect=real_select_for_update
            ) as select_for_update,
            patch.object(Draft, "build_rounds", side_effect=record_atomic),
        ):
            resp = self.post()

        self.assertEqual(resp.status_code, 201)
        select_for_update.assert_called()
        self.assertEqual(seen, [True])

    def test_rebuild_team_atomic_with_non_member_captain(self) -> None:
        self.team_a.members.set([self.p1])
        self.team_a.captain = self.cap_a
        self.team_a.save()
        game = Game.objects.create(tournament=self.tournament, radiant_team=self.team_a)
        with patch("app.functions.tournament.notify_draft_started") as notify:
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
