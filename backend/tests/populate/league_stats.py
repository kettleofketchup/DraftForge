"""
Strip league stats test data population.

Deterministic Steam league-ticket history for the strip stats column and the
player panel summary. See tests/data/league_stats.py for the per-user result
sequences. Runs last in populate_all with pinned pks (org 20, league 20,
tournament 250) so no existing autoincrement pk shifts.
"""

import math
import random
from datetime import date

from django.db import transaction

from app.models import (
    CustomUser,
    Draft,
    DraftOptions,
    League,
    Organization,
    PositionsModel,
    Team,
    TeamDraftState,
    Tournament,
)
from league.models import LeagueUser
from steam.functions.stats_update import update_all_league_stats_for_league
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats
from tests.data.league_stats import (
    SHOWCASE_CAPTAIN_COUNT,
    SHOWCASE_MATCH_COUNT,
    SHOWCASE_MATCH_ID_BASE,
    SHOWCASE_MATCH_ID_MAX,
    SHOWCASE_PLAYERS,
    SHOWCASE_SEED,
    SHOWCASE_START_TIME_BASE,
    SHOWCASE_TOURNAMENT_NAME,
    SHOWCASE_TOURNAMENT_PK,
    STRIP_STATS_MATCH_ID_BASE,
    STRIP_STATS_MATCH_ID_MAX,
    STRIP_STATS_PLAYERS,
    STRIP_STATS_START_TIME_BASE,
    STRIP_STATS_TOURNAMENT_NAME,
    STRIP_STATS_TOURNAMENT_PK,
    ShowcasePlayer,
    StripStatsPlayer,
)
from tests.data.leagues import SHOWCASE_LEAGUE, STRIP_STATS_LEAGUE
from tests.data.models import TestLeague, TestOrganization, TestUser
from tests.data.organizations import SHOWCASE_ORG, STRIP_STATS_ORG
from tests.data.users import ADMIN_USER

from .utils import delete_ledger_for_users, ensure_org_user, flush_redis_cache

RADIANT_SLOT = 0
DIRE_SLOT = 128


def _ensure_org_and_league(
    org_data: TestOrganization, league_data: TestLeague
) -> tuple[Organization, League]:
    org, _ = Organization.objects.update_or_create(
        name=org_data.name,
        defaults={
            "pk": org_data.pk,
            "description": org_data.description,
            "logo": "",
            "rules_template": org_data.rules_template,
            "timezone": org_data.timezone,
        },
    )
    assert org.pk == org_data.pk, f"{org_data.name} pk {org.pk}"

    league, _ = League.objects.update_or_create(
        steam_league_id=league_data.steam_league_id,
        defaults={
            "pk": league_data.pk,
            "organization": org,
            "name": league_data.name,
            "description": league_data.description,
            "rules": league_data.rules,
            "prize_pool": "",
            "timezone": league_data.timezone,
        },
    )
    assert league.pk == league_data.pk, f"{league_data.name} pk {league.pk}"

    if org.default_league_id != league.pk:
        org.default_league = league
        org.save()

    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user:
        org.admins.add(admin_user)
    return org, league


def _ensure_user(data: TestUser, force: bool) -> CustomUser:
    existing = CustomUser.objects.filter(pk=data.pk).first()
    if existing and existing.username != data.username:
        raise RuntimeError(
            f"pk {data.pk} held by {existing.username}, expected {data.username}"
        )
    if existing and not force:
        return existing
    if existing:
        delete_ledger_for_users([existing.pk])
        existing.delete()

    user = CustomUser(
        pk=data.pk,
        username=data.username,
        nickname=data.nickname,
        discordId=data.discord_id,
        steamid=data.get_steam_id_64(),
        positions=PositionsModel.objects.create(),
    )
    user.set_unusable_password()
    user.save()
    return user


def _build_matches(
    users: list[tuple[StripStatsPlayer, CustomUser]],
) -> tuple[list[Match], list[PlayerMatchStats]]:
    matches: list[Match] = []
    stats: list[PlayerMatchStats] = []
    for player, user in users:
        for result in player.sequence:
            index = len(matches) + 1
            won = result == "W"
            match = Match(
                match_id=STRIP_STATS_MATCH_ID_BASE + index,
                radiant_win=won,
                duration=2400,
                start_time=STRIP_STATS_START_TIME_BASE + index * 3600,
                game_mode=2,
                lobby_type=1,
                league_id=STRIP_STATS_LEAGUE.steam_league_id,
            )
            matches.append(match)
            stats.append(
                PlayerMatchStats(
                    match=match,
                    steam_id=user.steamid,
                    user=user,
                    player_slot=RADIANT_SLOT if index % 2 else DIRE_SLOT,
                    hero_id=index % 120 + 1,
                    kills=8 if won else 3,
                    deaths=3 if won else 8,
                    assists=10,
                    gold_per_min=520 if won else 410,
                    xp_per_min=600 if won else 480,
                    last_hits=200,
                    denies=10,
                    hero_damage=20000,
                    tower_damage=3000 if won else 500,
                    hero_healing=0,
                )
            )
            if stats[-1].player_slot == DIRE_SLOT:
                match.radiant_win = not won
    return matches, stats


def populate_league_stats_data(force: bool = False) -> None:
    print("Populating strip league stats test data...")
    org, league = _ensure_org_and_league(STRIP_STATS_ORG, STRIP_STATS_LEAGUE)

    users = [
        (player, _ensure_user(player.user, force)) for player in STRIP_STATS_PLAYERS
    ]

    for player, user in users:
        org_user = ensure_org_user(user, org, mmr=player.org_mmr)
        LeagueUser.objects.update_or_create(
            user=user,
            league=league,
            defaults={"org_user": org_user, "mmr": player.league_mmr},
        )

    Tournament.objects.filter(pk=STRIP_STATS_TOURNAMENT_PK).delete()
    Tournament.objects.filter(name=STRIP_STATS_TOURNAMENT_NAME).delete()
    tournament = Tournament.objects.create(
        pk=STRIP_STATS_TOURNAMENT_PK,
        name=STRIP_STATS_TOURNAMENT_NAME,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=STRIP_STATS_LEAGUE.steam_league_id,
    )
    tournament.users.set([user for _, user in users])

    captains = [user for player, user in users if player.captain]
    for order, captain in enumerate(captains, start=1):
        team = Team.objects.create(
            tournament=tournament,
            name=f"Strip Team {captain.username.removeprefix('strip_')}",
            captain=captain,
            draft_order=order,
        )
        team.members.set([captain])

    DraftOptions.ensure_for(tournament, timer_enabled=False)
    draft = Draft.objects.create(tournament=tournament, draft_style="snake")
    draft.build_rounds()
    draft.state = TeamDraftState.DRAFTING
    draft.save(update_fields=["state"])

    matches, stats = _build_matches(users)
    with transaction.atomic():
        Match.objects.filter(
            match_id__gt=STRIP_STATS_MATCH_ID_BASE,
            match_id__lte=STRIP_STATS_MATCH_ID_MAX,
        ).delete()
        LeaguePlayerStats.objects.filter(
            league_id=STRIP_STATS_LEAGUE.steam_league_id
        ).delete()
        Match.objects.bulk_create(matches)
        PlayerMatchStats.objects.bulk_create(stats)
    update_all_league_stats_for_league(STRIP_STATS_LEAGUE.steam_league_id)

    print(
        f"  Created '{tournament.name}' (pk={tournament.pk}), league pk={league.pk}, "
        f"{len(matches)} ticket matches"
    )
    flush_redis_cache()


TEAM_SIZE = 5
SKILL_WEIGHT = 0.6


def _showcase_lineups() -> (
    list[tuple[list[ShowcasePlayer], list[ShowcasePlayer], bool]]
):
    """Seeded 5v5 lineups; the stronger side is more likely, not certain, to win."""
    rng = random.Random(SHOWCASE_SEED)
    regulars = [p for p in SHOWCASE_PLAYERS if p.fixed_games is None]
    newcomers = [p for p in SHOWCASE_PLAYERS if p.fixed_games]
    lineups: list[tuple[list[ShowcasePlayer], list[ShowcasePlayer], bool]] = []
    for index in range(SHOWCASE_MATCH_COUNT):
        joining = [p for p in newcomers if index < (p.fixed_games or 0)]
        ranked = sorted(
            regulars, key=lambda p: rng.random() ** (1.0 / p.activity), reverse=True
        )
        lineup = joining + ranked[: TEAM_SIZE * 2 - len(joining)]
        rng.shuffle(lineup)
        radiant, dire = lineup[:TEAM_SIZE], lineup[TEAM_SIZE:]
        gap = sum(p.skill for p in radiant) - sum(p.skill for p in dire)
        radiant_win = rng.random() < 1 / (1 + math.exp(-SKILL_WEIGHT * gap))
        lineups.append((radiant, dire, radiant_win))
    return lineups


def _build_showcase_matches(
    users: dict[int, CustomUser],
) -> tuple[list[Match], list[PlayerMatchStats]]:
    rng = random.Random(SHOWCASE_SEED + 1)
    matches: list[Match] = []
    stats: list[PlayerMatchStats] = []
    for index, (radiant, dire, radiant_win) in enumerate(_showcase_lineups(), start=1):
        match = Match(
            match_id=SHOWCASE_MATCH_ID_BASE + index,
            radiant_win=radiant_win,
            duration=rng.randint(1500, 3300),
            start_time=SHOWCASE_START_TIME_BASE + index * 3600,
            game_mode=2,
            lobby_type=1,
            league_id=SHOWCASE_LEAGUE.steam_league_id,
        )
        matches.append(match)
        for side, base_slot, won in (
            (radiant, RADIANT_SLOT, radiant_win),
            (dire, DIRE_SLOT, not radiant_win),
        ):
            for offset, player in enumerate(side):
                user = users[player.user.pk]
                stats.append(
                    PlayerMatchStats(
                        match=match,
                        steam_id=user.steamid,
                        user=user,
                        player_slot=base_slot + offset,
                        hero_id=rng.randint(1, 120),
                        kills=rng.randint(4, 14) if won else rng.randint(1, 8),
                        deaths=rng.randint(1, 6) if won else rng.randint(4, 12),
                        assists=rng.randint(5, 20),
                        gold_per_min=rng.randint(420, 680)
                        if won
                        else rng.randint(300, 520),
                        xp_per_min=rng.randint(480, 760)
                        if won
                        else rng.randint(360, 600),
                        last_hits=rng.randint(40, 320),
                        denies=rng.randint(0, 20),
                        hero_damage=rng.randint(8000, 40000),
                        tower_damage=rng.randint(500, 8000)
                        if won
                        else rng.randint(0, 2500),
                        hero_healing=rng.randint(0, 4000),
                    )
                )
    return matches, stats


def populate_league_stats_showcase(force: bool = False) -> None:
    print("Populating league stats showcase data...")
    org, league = _ensure_org_and_league(SHOWCASE_ORG, SHOWCASE_LEAGUE)

    users = {p.user.pk: _ensure_user(p.user, force) for p in SHOWCASE_PLAYERS}
    for player in SHOWCASE_PLAYERS:
        user = users[player.user.pk]
        org_user = ensure_org_user(user, org, mmr=player.org_mmr)
        LeagueUser.objects.update_or_create(
            user=user,
            league=league,
            defaults={"org_user": org_user, "mmr": player.org_mmr},
        )

    Tournament.objects.filter(pk=SHOWCASE_TOURNAMENT_PK).delete()
    Tournament.objects.filter(name=SHOWCASE_TOURNAMENT_NAME).delete()
    tournament = Tournament.objects.create(
        pk=SHOWCASE_TOURNAMENT_PK,
        name=SHOWCASE_TOURNAMENT_NAME,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=SHOWCASE_LEAGUE.steam_league_id,
    )
    tournament.users.set(users.values())

    captains = sorted(
        (p for p in SHOWCASE_PLAYERS if p.fixed_games is None),
        key=lambda p: p.org_mmr,
        reverse=True,
    )[:SHOWCASE_CAPTAIN_COUNT]
    for order, player in enumerate(captains, start=1):
        captain = users[player.user.pk]
        team = Team.objects.create(
            tournament=tournament,
            name=f"Showcase Team {order}",
            captain=captain,
            draft_order=order,
        )
        team.members.set([captain])

    DraftOptions.ensure_for(tournament, timer_enabled=False)
    draft = Draft.objects.create(tournament=tournament, draft_style="snake")
    draft.build_rounds()
    draft.state = TeamDraftState.DRAFTING
    draft.save(update_fields=["state"])

    matches, stats = _build_showcase_matches(users)
    with transaction.atomic():
        Match.objects.filter(
            match_id__gt=SHOWCASE_MATCH_ID_BASE, match_id__lte=SHOWCASE_MATCH_ID_MAX
        ).delete()
        LeaguePlayerStats.objects.filter(
            league_id=SHOWCASE_LEAGUE.steam_league_id
        ).delete()
        Match.objects.bulk_create(matches)
        PlayerMatchStats.objects.bulk_create(stats)
    update_all_league_stats_for_league(SHOWCASE_LEAGUE.steam_league_id)

    print(
        f"  Created '{tournament.name}' (pk={tournament.pk}), league pk={league.pk}, "
        f"{len(matches)} ticket matches, {len(users)} players"
    )
    flush_redis_cache()
