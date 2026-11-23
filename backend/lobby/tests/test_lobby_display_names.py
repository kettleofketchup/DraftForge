from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.models import CustomUser
from league.models import League
from lobby import services
from lobby.tests.helpers import (
    lobby_settings,
    make_game,
    make_team,
    make_tournament,
    make_user,
)
from lobby.views import _players
from org.models import Organization, OrgUser
from tournament.choices import DotaLobbyMode
from tournament.models import Game


@lobby_settings
class LobbyDisplayNamesTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="LDN Org", members_private=True)
        self.other_org = Organization.objects.create(name="LDN Other Org")
        league = League.objects.create(
            name="LDN League", organization=self.org, steam_league_id=77201
        )
        self.tournament = make_tournament(
            dota_lobby_mode=DotaLobbyMode.MANUAL, league=league
        )
        self.game = make_game(self.tournament)
        self.staff = make_user()
        self.staff.is_staff = True
        self.staff.save()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _roster(self, game: Game) -> list[CustomUser]:
        users: list[CustomUser] = []
        for team in (game.radiant_team, game.dire_team):
            users.extend(services.team_roster(team))
        return users

    def _name_all(self, users: list[CustomUser]) -> None:
        for user in users:
            user.discordNickname = f"global_{user.pk}"
            user.save()
            user.nickname = f"site_{user.pk}"
            OrgUser.objects.create(
                user=user, organization=self.org, guild_nickname=f"server_{user.pk}"
            )
            OrgUser.objects.create(
                user=user,
                organization=self.other_org,
                guild_nickname=f"elsewhere_{user.pk}",
            )

    def test_players_use_tournament_org_server_nickname(self) -> None:
        roster = self._roster(self.game)
        self._name_all(roster)
        resp = self.client.get(f"/api/games/{self.game.pk}/lobby/")
        self.assertEqual(resp.status_code, 200)
        names = {row["user_id"]: row["name"] for row in resp.data["players"]}
        self.assertEqual(names, {u.pk: f"server_{u.pk}" for u in roster})

    def test_falls_back_to_global_chain_without_server_nickname(self) -> None:
        roster = self._roster(self.game)
        dragon = roster[0]
        dragon.discordNickname = "Gwaihir"
        dragon.save()
        dragon.nickname = "SiteDragon"
        other = roster[2]
        other.discordNickname = "Windlord"
        other.save()
        resp = self.client.get(f"/api/games/{self.game.pk}/lobby/")
        names = {row["user_id"]: row["name"] for row in resp.data["players"]}
        self.assertEqual(names[dragon.pk], "Gwaihir")
        self.assertEqual(names[other.pk], "Windlord")
        self.assertEqual(names[roster[1].pk], roster[1].username)

    def test_missing_players_use_server_nickname(self) -> None:
        no_steam = make_user(steam=False)
        self.game.dire_team.members.add(no_steam)
        OrgUser.objects.create(
            user=no_steam, organization=self.org, guild_nickname="NoSteamNick"
        )
        resp = self.client.get(f"/api/games/{self.game.pk}/lobby/")
        missing = resp.data["eligibility"]["details"]["players"]
        self.assertEqual(missing, [{"id": no_steam.pk, "name": "NoSteamNick"}])

    def test_query_count_does_not_grow_with_players(self) -> None:
        small = Game.objects.create(
            tournament=self.tournament,
            radiant_team=make_team(self.tournament, "Wrens", size=1),
            dire_team=make_team(self.tournament, "Jays", size=1),
            round=3,
        )
        self._name_all(self._roster(small))
        self._name_all(self._roster(self.game))
        counts: list[int] = []
        for game in (small, self.game):
            fresh = Game.objects.select_related(
                "tournament__league", "radiant_team", "dire_team"
            ).get(pk=game.pk)
            with CaptureQueriesContext(connection) as ctx:
                rows = _players(fresh, None)
            self.assertTrue(all(r["name"].startswith("server_") for r in rows))
            counts.append(len(ctx.captured_queries))
        self.assertEqual(counts[0], counts[1])
