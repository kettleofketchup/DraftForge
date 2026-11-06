"""
Strip league stats test data population.

Deterministic Steam league-ticket history for the strip stats column and the
player panel summary. See tests/data/league_stats.py for the per-user result
sequences. Runs last in populate_all with pinned pks (org 20, league 20,
tournament 250) so no existing autoincrement pk shifts.
"""

from datetime import date

from django.db import transaction

from app.models import (
    CustomUser,
    Draft,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from league.models import LeagueUser
from steam.functions.stats_update import update_all_league_stats_for_league
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats
from tests.data.league_stats import (
    STRIP_STATS_MATCH_ID_BASE,
    STRIP_STATS_MATCH_ID_MAX,
    STRIP_STATS_PLAYERS,
    STRIP_STATS_START_TIME_BASE,
    STRIP_STATS_TOURNAMENT_NAME,
    STRIP_STATS_TOURNAMENT_PK,
    StripStatsPlayer,
)
from tests.data.leagues import STRIP_STATS_LEAGUE
from tests.data.organizations import STRIP_STATS_ORG
from tests.data.users import ADMIN_USER

from .utils import ensure_org_user, flush_redis_cache

RADIANT_SLOT = 0
DIRE_SLOT = 128


def _ensure_org_and_league() -> tuple[Organization, League]:
    org, _ = Organization.objects.update_or_create(
        name=STRIP_STATS_ORG.name,
        defaults={
            "pk": STRIP_STATS_ORG.pk,
            "description": STRIP_STATS_ORG.description,
            "logo": "",
            "rules_template": STRIP_STATS_ORG.rules_template,
            "timezone": STRIP_STATS_ORG.timezone,
        },
    )
    assert org.pk == STRIP_STATS_ORG.pk, f"Strip Stats Org pk {org.pk}"

    league, _ = League.objects.update_or_create(
        steam_league_id=STRIP_STATS_LEAGUE.steam_league_id,
        defaults={
            "pk": STRIP_STATS_LEAGUE.pk,
            "organization": org,
            "name": STRIP_STATS_LEAGUE.name,
            "description": STRIP_STATS_LEAGUE.description,
            "rules": STRIP_STATS_LEAGUE.rules,
            "prize_pool": "",
            "timezone": STRIP_STATS_LEAGUE.timezone,
        },
    )
    assert league.pk == STRIP_STATS_LEAGUE.pk, f"Strip Stats League pk {league.pk}"

    if org.default_league_id != league.pk:
        org.default_league = league
        org.save()

    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user:
        org.admins.add(admin_user)
    return org, league


def _ensure_user(player: StripStatsPlayer, force: bool) -> CustomUser:
    data = player.user
    existing = CustomUser.objects.filter(pk=data.pk).first()
    if existing and existing.username != data.username:
        raise RuntimeError(
            f"pk {data.pk} held by {existing.username}, expected {data.username}"
        )
    if existing and not force:
        return existing
    if existing:
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
    org, league = _ensure_org_and_league()

    users = [(player, _ensure_user(player, force)) for player in STRIP_STATS_PLAYERS]

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

    draft = Draft.objects.create(tournament=tournament, draft_style="snake")
    draft.build_rounds()

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
