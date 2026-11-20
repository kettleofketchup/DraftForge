from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.functions.shuffle_draft import get_lowest_mmr_team, get_team_total_mmr
from app.models import (
    CustomUser,
    Draft,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from app.services.team_leadership import successor_after_removal
from common.game import GameType
from events.models import Event
from events.services import create_tournament_for_event
from org.mmr import set_org_mmr
from org.models import OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from user.tests.test_cacheops_integration import _redis_reachable


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=f"discord_{name}",
        positions=PositionsModel.objects.create(),
    )


class CaptainSuccessionRegressionTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Pin Org")
        self.league = League.objects.create(name="Pin League", organization=self.org)
        self.tournament = Tournament.objects.create(
            name="Pin Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
            league=self.league,
        )
        self.users = [_make_user(f"pin_{i}") for i in range(4)]
        self.team = Team.objects.create(tournament=self.tournament, name="Pin Team")
        self.team.members.set(self.users)
        Team.objects.filter(pk=self.team.pk).update(captain=self.users[0])
        self.team.refresh_from_db()

    def _remove_captain(self) -> set[int]:
        Team.members.through.objects.filter(
            team=self.team, customuser=self.users[0]
        ).delete()
        return {self.users[0].pk}

    def test_all_zero_team_returns_org_user_member(self) -> None:
        for user in self.users[1:]:
            ensure_org_user(user, self.org, mmr=0)

        captain, deputy, how = successor_after_removal(
            self.team, self._remove_captain()
        )

        self.assertEqual(how, "org_mmr")
        self.assertIsNone(deputy)
        self.assertIn(captain, self.users[1:])

    def test_zero_mmr_org_user_beats_member_without_org_user(self) -> None:
        ensure_org_user(self.users[3], self.org, mmr=0)

        captain, deputy, how = successor_after_removal(
            self.team, self._remove_captain()
        )

        self.assertEqual((captain, deputy, how), (self.users[3], None, "org_mmr"))
        self.assertFalse(
            OrgUser.objects.filter(user=self.users[1], organization=self.org).exists()
        )


class GameOrgMmrFixtures:
    org: Organization
    league: League
    admin: CustomUser
    dota_tournament: Tournament
    dl_tournament: Tournament

    def build_orgs(self) -> None:
        self.admin = _make_user("gm_admin")
        self.org = Organization.objects.create(name="Game MMR Org", owner=self.admin)
        self.league = League.objects.create(
            name="Game MMR League", organization=self.org
        )
        self.dota_tournament = Tournament.objects.create(
            name="Dota Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
            league=self.league,
        )
        event = Event.objects.create(
            name="Deadlock Night",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.admin,
            tournament_name="Deadlock Cup",
            tournament_league=self.league,
            game_type=GameType.DEADLOCK,
        )
        self.dl_tournament = create_tournament_for_event(event)
        assert self.dl_tournament.league_id == self.league.pk
        assert self.dl_tournament.game_type == GameType.DEADLOCK

    def member(self, name: str, dota: int, deadlock: int) -> CustomUser:
        user = _make_user(name)
        ensure_org_user(
            user, self.org, mmr=dota, game_mmrs={GameType.DEADLOCK: deadlock}
        )
        return user

    def team(
        self,
        tournament: Tournament,
        name: str,
        captain: CustomUser,
        members: list[CustomUser] | None = None,
        draft_order: int = 0,
    ) -> Team:
        team = Team.objects.create(
            name=name,
            captain=captain,
            tournament=tournament,
            draft_order=draft_order,
        )
        team.members.add(captain, *(members or []))
        return team


class GameOrgMmrDraftTests(GameOrgMmrFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.a = self.member("gm_a", 5000, 1000)
        self.b = self.member("gm_b", 1000, 5000)

    def test_deadlock_shuffle_order_uses_deadlock(self) -> None:
        dota_a = self.team(self.dota_tournament, "Dota A", self.a)
        dota_b = self.team(self.dota_tournament, "Dota B", self.b)
        dl_a = self.team(self.dl_tournament, "DL A", self.a)
        dl_b = self.team(self.dl_tournament, "DL B", self.b)

        self.assertEqual(get_lowest_mmr_team([dota_a, dota_b]), (dota_b, None))
        self.assertEqual(get_lowest_mmr_team([dl_a, dl_b]), (dl_a, None))

    def test_team_total_mmr_per_game(self) -> None:
        dota = self.team(self.dota_tournament, "Dota", self.a, [self.b])
        dl = self.team(self.dl_tournament, "DL", self.a, [self.b])
        c = self.member("gm_c", 3000, 200)
        dota.members.add(c)
        dl.members.add(c)

        self.assertEqual(get_team_total_mmr(dota), 9000)
        self.assertEqual(get_team_total_mmr(dl), 6200)

    def test_team_total_mmr_one_query(self) -> None:
        others = [self.member(f"gm_q{i}", 100 * i, 10 * i) for i in range(1, 4)]
        team = self.team(self.dl_tournament, "DL Five", self.a, [self.b, *others])
        team = Team.objects.get(pk=team.pk)

        with CaptureQueriesContext(connection) as ctx:
            total = get_team_total_mmr(team)

        game_queries = [
            q for q in ctx.captured_queries if "org_orgusergamemmr" in q["sql"]
        ]
        self.assertEqual(len(game_queries), 1)
        self.assertEqual(total, 1000 + 5000 + 10 + 20 + 30)

    def test_create_next_shuffle_round_uses_tournament_game(self) -> None:
        self.dl_tournament.users.add(self.a, self.b)
        self.team(self.dl_tournament, "DL A", self.a)
        team_b = self.team(self.dl_tournament, "DL B", self.b)
        draft, _ = Draft.objects.get_or_create(
            tournament=self.dl_tournament, defaults={"draft_style": "shuffle"}
        )

        result = draft.create_next_shuffle_round()

        self.assertNotEqual(result["round"].captain_id, team_b.captain_id)
        self.assertEqual(result["team_mmr"], 1000)

    def test_simulate_draft_uses_tournament_game(self) -> None:
        cap1 = self.member("gm_cap1", 300, 300)
        cap2 = self.member("gm_cap2", 200, 200)
        for tournament in (self.dota_tournament, self.dl_tournament):
            tournament.users.add(cap1, cap2, self.a, self.b)
            self.team(tournament, f"{tournament.pk} one", cap1, draft_order=1)
            self.team(tournament, f"{tournament.pk} two", cap2, draft_order=2)

        dota_sim = Draft.objects.get_or_create(tournament=self.dota_tournament)[
            0
        ]._simulate_draft("snake")
        dl_sim = Draft.objects.get_or_create(tournament=self.dl_tournament)[
            0
        ]._simulate_draft("snake")

        dota_first = self.dota_tournament.teams.get(draft_order=1)
        dl_first = self.dl_tournament.teams.get(draft_order=1)
        self.assertEqual(dota_sim[dota_first.pk], [(cap1.pk, 300), (self.a.pk, 5000)])
        self.assertEqual(dl_sim[dl_first.pk], [(cap1.pk, 300), (self.b.pk, 5000)])


class GameOrgMmrSuccessionTests(GameOrgMmrFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()

    def _team_after_captain_removed(
        self, tournament: Tournament, members: list[CustomUser]
    ) -> tuple[Team, set[int]]:
        captain = _make_user(f"gm_old_cap_{tournament.pk}")
        team = self.team(tournament, f"Succ {tournament.pk}", captain, members)
        Team.members.through.objects.filter(team=team, customuser=captain).delete()
        return team, {captain.pk}

    def test_captain_succession_deadlock(self) -> None:
        a = self.member("gm_sa", 5000, 1000)
        b = self.member("gm_sb", 1000, 5000)
        dl_team, dl_removed = self._team_after_captain_removed(
            self.dl_tournament, [a, b]
        )
        dota_team, dota_removed = self._team_after_captain_removed(
            self.dota_tournament, [a, b]
        )

        self.assertEqual(
            successor_after_removal(dl_team, dl_removed), (b, None, "org_mmr")
        )
        self.assertEqual(
            successor_after_removal(dota_team, dota_removed), (a, None, "org_mmr")
        )

    def test_captain_succession_tie_lower_pk_wins(self) -> None:
        first = _make_user("gm_tie_first")
        second = _make_user("gm_tie_second")
        ensure_org_user(second, self.org, mmr=4000)
        ensure_org_user(first, self.org, mmr=4000)
        team, removed = self._team_after_captain_removed(
            self.dota_tournament, [first, second]
        )

        self.assertEqual(
            successor_after_removal(team, removed), (second, None, "org_mmr")
        )


class GameOrgMmrEdgeTests(GameOrgMmrFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()

    def test_member_without_org_user_counts_zero(self) -> None:
        a = self.member("gm_ea", 5000, 1000)
        outsider = _make_user("gm_outsider")
        team = self.team(self.dl_tournament, "DL Edge", a, [outsider])

        self.assertFalse(
            OrgUser.objects.filter(user=outsider, organization=self.org).exists()
        )
        self.assertEqual(get_team_total_mmr(team), 1000)

    def test_tournament_without_org_total_zero(self) -> None:
        a = self.member("gm_na", 5000, 1000)
        orphan = Tournament.objects.create(
            name="No League",
            tournament_type="single_elimination",
            date_played=timezone.now(),
            game_type=GameType.DEADLOCK,
        )
        team = self.team(orphan, "Orphan", a)

        self.assertEqual(get_team_total_mmr(team), 0)

    def test_event_tournament_without_league_keeps_today(self) -> None:
        event = Event.objects.create(
            name="Leagueless DL",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.admin,
            game_type=GameType.DEADLOCK,
        )
        tournament = create_tournament_for_event(event)
        self.assertIsNone(tournament.league)
        low = self.member("gm_low", 100, 100)
        high = self.member("gm_high", 9000, 9000)
        captain = _make_user("gm_ll_cap")
        team = self.team(tournament, "Leagueless", captain, [low, high])
        self.assertEqual(get_team_total_mmr(team), 0)

        Team.members.through.objects.filter(team=team, customuser=captain).delete()
        self.assertEqual(
            successor_after_removal(team, {captain.pk}), (low, None, "lowest_pk")
        )


@override_settings(CACHEOPS_ENABLED=True)
class DraftStyleMmrsCacheTests(GameOrgMmrFixtures, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.build_orgs()
        self.client = APIClient()
        cap1 = self.member("gm_c1", 300, 700)
        cap2 = self.member("gm_c2", 200, 400)
        self.a = self.member("gm_ca", 5000, 1000)
        self.b = self.member("gm_cb", 1000, 5000)
        self.drafts: dict[int, Draft] = {}
        for tournament in (self.dota_tournament, self.dl_tournament):
            tournament.users.add(cap1, cap2, self.a, self.b)
            self.team(tournament, f"{tournament.pk} one", cap1, draft_order=1)
            self.team(tournament, f"{tournament.pk} two", cap2, draft_order=2)
            self.drafts[tournament.game_type] = Draft.objects.get_or_create(
                tournament=tournament
            )[0]

    def _style_mmrs(self, draft: Draft) -> dict:
        response = self.client.post(
            "/api/draft/get-style-mmrs", {"pk": draft.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_draft_style_mmrs_keyed_per_draft(self) -> None:
        dota = self._style_mmrs(self.drafts[GameType.DOTA2])
        deadlock = self._style_mmrs(self.drafts[GameType.DEADLOCK])

        self.assertEqual(dota["pk"], self.drafts[GameType.DOTA2].pk)
        self.assertEqual(deadlock["pk"], self.drafts[GameType.DEADLOCK].pk)
        self.assertEqual(dota["snake_first_pick_mmr"], 300 + 5000)
        self.assertEqual(deadlock["snake_first_pick_mmr"], 700 + 5000)
        self.assertEqual(dota["snake_last_pick_mmr"], 200 + 1000)
        self.assertEqual(deadlock["snake_last_pick_mmr"], 400 + 1000)

    def test_draft_style_mmrs_busted_by_set_org_mmr(self) -> None:
        draft = self.drafts[GameType.DEADLOCK]
        primed = self._style_mmrs(draft)
        self.assertEqual(primed["snake_last_pick_mmr"], 400 + 1000)

        org_user = OrgUser.objects.get(user=self.a, organization=self.org)
        set_org_mmr(org_user, GameType.DEADLOCK, 1500, mark_verified=False)

        self.assertEqual(self._style_mmrs(draft)["snake_last_pick_mmr"], 400 + 1500)

    def test_draft_style_mmrs_busted_by_game_mmr_row_save(self) -> None:
        draft = self.drafts[GameType.DEADLOCK]
        self.assertEqual(self._style_mmrs(draft)["snake_last_pick_mmr"], 400 + 1000)

        row = OrgUserGameMmr.objects.get(
            org_user__user=self.a,
            org_user__organization=self.org,
            game_type=GameType.DEADLOCK,
        )
        row.mmr = 1700
        row.save()

        self.assertEqual(self._style_mmrs(draft)["snake_last_pick_mmr"], 400 + 1700)
