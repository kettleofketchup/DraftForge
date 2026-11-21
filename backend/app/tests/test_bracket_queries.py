"""Query budget and output parity for GET /api/bracket/tournaments/<id>/."""

import itertools
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.db import connection
from django.db.models import Q
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Game,
    GameType,
    League,
    Organization,
    Team,
    Tournament,
)
from app.serializers import BracketGameSerializer
from draft.models import HeroDraft
from league.models import LeagueUser
from lobby.models import GameLobby
from org.mmr import set_org_mmr
from org.models import OrgUser

TEAM_SIZE = 5
_user_ids = itertools.count(100_000)
# tournament, league, org, games, lobbies, herodrafts, 3 roster tables,
# org users, league users, org user game MMRs
# +1: OrgUserGameMmr prefetch
BRACKET_QUERIES = 12
# insert missing org users, then reread them with their league users and
# game MMRs (+1: OrgUserGameMmr prefetch on the reread)
ORG_USER_CREATE_QUERIES = 4

# (bracket_type, round, games in round)
DOUBLE_ELIM_8: tuple[tuple[str, int, int], ...] = (
    ("winners", 1, 4),
    ("winners", 2, 2),
    ("winners", 3, 1),
    ("losers", 1, 2),
    ("losers", 2, 2),
    ("losers", 3, 1),
    ("losers", 4, 1),
    ("grand_finals", 1, 1),
)


@dataclass
class BracketFixture:
    tournament: Tournament
    teams: list[Team]
    games: list[Game]


def build_bracket(
    prefix: str, *, team_count: int = 8, with_org: bool = True
) -> BracketFixture:
    """Double-elimination bracket with full rosters, lobbies and a hero draft."""
    league = None
    org = None
    if with_org:
        org = Organization.objects.create(name=f"{prefix} Org")
        league = League.objects.create(name=f"{prefix} League", organization=org)
    tournament = Tournament.objects.create(
        name=f"{prefix} Cup",
        date_played=datetime(2026, 11, 14, tzinfo=UTC),
        league=league,
        tournament_type="double_elimination",
    )

    teams: list[Team] = []
    for t in range(team_count):
        roster = [
            CustomUser.objects.create_user(
                username=f"{prefix}-t{t}-p{p}",
                discordId=str(next(_user_ids) * 7),
                steam_account_id=next(_user_ids),
            )
            for p in range(TEAM_SIZE + 2)
        ]
        for i, user in enumerate(roster):
            user.nickname = f"{prefix} nick {t}.{i}"
        members, dropin, left = roster[:TEAM_SIZE], roster[TEAM_SIZE], roster[-1]
        team = Team.objects.create(
            name=f"{prefix} Team {t}",
            tournament=tournament,
            captain=members[0],
            deputy_captain=members[1],
            draft_order=t,
        )
        # Reverse insertion so roster order differs from pk order.
        team.members.add(*reversed(members))
        team.dropin_members.add(dropin)
        team.left_members.add(left)
        tournament.users.add(*roster)
        teams.append(team)

    if org is not None:
        for i, org_user in enumerate(
            OrgUser.objects.filter(organization=org).order_by("pk")
        ):
            set_org_mmr(org_user, GameType.DOTA2, 2000 + i * 37, mark_verified=False)
            if i % 3 == 0:
                LeagueUser.objects.update_or_create(
                    user_id=org_user.user_id,
                    league=league,
                    defaults={"org_user": org_user, "mmr": 3000 + i},
                )
        # Users without an OrgUser exercise the auto-create path, and the
        # recreated rows put orgUserPk order out of step with user pk order.
        OrgUser.objects.filter(
            Q(user__username__endswith="-p2") | Q(user__username__endswith="-p6"),
            organization=org,
        ).delete()

    games: list[Game] = []
    for bracket_type, round_number, count in DOUBLE_ELIM_8:
        for position in range(count):
            games.append(
                Game.objects.create(
                    tournament=tournament,
                    bracket_type=bracket_type,
                    elimination_type="double",
                    round=round_number,
                    position=position,
                )
            )
    first_round = [g for g in games if g.bracket_type == "winners" and g.round == 1]
    for i, game in enumerate(first_round):
        game.radiant_team = teams[(2 * i) % team_count]
        game.dire_team = teams[(2 * i + 1) % team_count]
        game.next_game = games[4 + i // 2]
        game.next_game_slot = "radiant" if i % 2 == 0 else "dire"
        game.loser_next_game = games[7 + i // 2]
        game.loser_next_game_slot = "radiant" if i % 2 == 0 else "dire"
        if i < 2:
            game.winning_team = game.radiant_team
            game.status = "completed"
        game.save()
    games[4].radiant_team = teams[0]
    games[4].dire_team = teams[2 % team_count]
    games[4].save()

    HeroDraft.objects.create(game=first_round[2])
    GameLobby.objects.create(
        game=first_round[0],
        external_ref=f"{prefix}-a",
        state=GameLobby.State.TIMED_OUT,
    )
    GameLobby.objects.create(
        game=first_round[0],
        external_ref=f"{prefix}-b",
        state=GameLobby.State.WAITING,
    )
    GameLobby.objects.create(game=first_round[3], external_ref=f"{prefix}-c")
    return BracketFixture(tournament=tournament, teams=teams, games=games)


def per_team_serialization(tournament: Tournament) -> list[dict[str, Any]]:
    """The serializer's standalone path: each team field queries on its own."""
    games = Game.objects.filter(tournament=tournament).order_by(
        "bracket_type", "round", "position"
    )
    return json.loads(json.dumps(BracketGameSerializer(games, many=True).data))


@override_settings(CACHEOPS_ENABLED=False)
class BracketQueryTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def get_bracket(self, tournament: Tournament) -> tuple[bytes, int]:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(f"/api/bracket/tournaments/{tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.content, len(ctx)

    def test_query_count_is_fixed(self) -> None:
        fx = build_bracket("big")
        _, first = self.get_bracket(fx.tournament)
        _, steady = self.get_bracket(fx.tournament)
        self.assertEqual(first, BRACKET_QUERIES + ORG_USER_CREATE_QUERIES)
        self.assertEqual(steady, BRACKET_QUERIES)

    def test_query_count_without_org(self) -> None:
        fx = build_bracket("plain", with_org=False)
        # source event and users replace league, org, org users, league users
        # and game MMRs
        self.assertEqual(self.get_bracket(fx.tournament)[1], BRACKET_QUERIES - 3)

    def test_query_count_does_not_grow_with_teams(self) -> None:
        small = build_bracket("small", team_count=4)
        big = build_bracket("big")
        self.get_bracket(small.tournament)
        self.get_bracket(big.tournament)
        self.assertEqual(
            self.get_bracket(small.tournament)[1], self.get_bracket(big.tournament)[1]
        )

    def test_matches_per_team_serialization_with_org(self) -> None:
        fx = build_bracket("org")
        org_users = OrgUser.objects.filter(
            organization=fx.tournament.league.organization
        )
        before = org_users.count()
        content, _ = self.get_bracket(fx.tournament)
        self.assertEqual(org_users.count(), before + 2 * len(fx.teams))
        body = json.loads(content)
        self.assertEqual(body["tournamentId"], fx.tournament.pk)
        self.assertEqual(
            json.dumps(body["matches"]),
            json.dumps(per_team_serialization(fx.tournament)),
        )

    def test_matches_per_team_serialization_without_org(self) -> None:
        fx = build_bracket("plain", with_org=False)
        content, _ = self.get_bracket(fx.tournament)
        self.assertEqual(
            json.dumps(json.loads(content)["matches"]),
            json.dumps(per_team_serialization(fx.tournament)),
        )
