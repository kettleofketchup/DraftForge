"""Internal API endpoints for Steam/match sync operations.

All endpoints require InternalServiceAuth (X-Internal-Token header).
"""

from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework import status
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]

SYNC_STATE_ALLOWED_FIELDS = {"is_syncing", "last_match_id", "failed_match_ids"}


@api_view(["GET", "PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def steam_sync_state(request, league_id):
    """GET: return (or create) sync state for a league. PATCH: update allowed fields."""
    from steam.models import LeagueSyncState

    if request.method == "GET":
        state, _created = LeagueSyncState.objects.get_or_create(league_id=league_id)
        return Response({
            "league_id": state.league_id,
            "is_syncing": state.is_syncing,
            "last_match_id": state.last_match_id,
            "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
            "failed_match_ids": state.failed_match_ids,
        })

    # PATCH
    state = LeagueSyncState.objects.get(league_id=league_id)
    for field in SYNC_STATE_ALLOWED_FIELDS:
        if field in request.data:
            setattr(state, field, request.data[field])
    state.last_sync_at = timezone.now()
    state.save()
    invalidate_after_commit(state)
    return Response({
        "league_id": state.league_id,
        "is_syncing": state.is_syncing,
        "last_match_id": state.last_match_id,
        "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
        "failed_match_ids": state.failed_match_ids,
    })


STEAM_ID_64_BASE = 76561197960265728


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def store_match(request):
    """Store a match and its player stats from raw Steam API data."""
    from app.models import CustomUser
    from steam.models import Match, PlayerMatchStats

    data = request.data
    match_id = data.get("match_id")
    league_id = data.get("league_id")
    if not match_id:
        log.warning(
            "steam_store_match_rejected",
            system="steam",
            subsystem="ingest",
            reason="missing_match_id",
            league_id=league_id,
        )
        return Response({"error": "match_id is required"}, status=400)

    # Create or update the Match record
    match, created = Match.objects.update_or_create(
        match_id=match_id,
        defaults={
            "radiant_win": data["radiant_win"],
            "duration": data["duration"],
            "start_time": data["start_time"],
            "game_mode": data["game_mode"],
            "lobby_type": data["lobby_type"],
            "league_id": league_id,
        },
    )

    players_stored = 0
    players_linked = 0
    players_skipped_no_account = 0

    for player in data.get("players", []):
        account_id = player.get("account_id")
        if not account_id:
            players_skipped_no_account += 1
            continue

        steam_id_64 = account_id + STEAM_ID_64_BASE

        stats, _ = PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=steam_id_64,
            defaults={
                "player_slot": player["player_slot"],
                "hero_id": player["hero_id"],
                "kills": player["kills"],
                "deaths": player["deaths"],
                "assists": player["assists"],
                "gold_per_min": player["gold_per_min"],
                "xp_per_min": player["xp_per_min"],
                "last_hits": player["last_hits"],
                "denies": player["denies"],
                "hero_damage": player["hero_damage"],
                "tower_damage": player["tower_damage"],
                "hero_healing": player["hero_healing"],
            },
        )

        # Link user by steamid
        try:
            user = CustomUser.objects.get(steamid=steam_id_64)
            stats.user = user
            stats.save(update_fields=["user"])
            players_linked += 1
        except CustomUser.DoesNotExist:
            pass

        players_stored += 1

    invalidate_after_commit(match)

    log.info(
        "steam_match_ingested",
        system="steam",
        subsystem="ingest",
        match_id=match_id,
        league_id=league_id,
        created=created,
        players_stored=players_stored,
        players_linked=players_linked,
        players_skipped_no_account=players_skipped_no_account,
    )

    return Response(
        {
            "match_id": match_id,
            "created": created,
            "players_stored": players_stored,
            "players_linked": players_linked,
        },
        status=201,
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def tracked_leagues(request):
    """Return League.steam_league_id values currently set on any League row.

    The periodic sync coordinator calls this to discover which leagues
    to poll — replaces the hardcoded LEAGUE_ID constant that previously
    pinned sync to a single league.
    """
    from app.models import League

    ids = list(
        League.objects.filter(steam_league_id__isnull=False)
        .values_list("steam_league_id", flat=True)
        .order_by("steam_league_id")
    )
    return Response({"steam_league_ids": ids})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_league_stats(request, league_id):
    """Recalculate LeaguePlayerStats for all users in a league."""
    from steam.functions.stats_update import update_all_league_stats_for_league

    updated_count = update_all_league_stats_for_league(league_id)
    return Response({"updated_count": updated_count})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def recalculate_mmr(request, user_id):
    """Recalculate a single user's league MMR."""
    from app.models import CustomUser
    from steam.functions.mmr_calculation import update_user_league_mmr

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    update_user_league_mmr(user)
    return Response({"user_id": user_id, "status": "recalculated"})
