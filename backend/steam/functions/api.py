import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from app.permissions_org import can_manage_game
from steam.constants import LEAGUE_ID
from steam.functions.game_linking import (
    auto_assign_matches_by_time,
    auto_link_matches_for_tournament,
    confirm_suggestion,
    dismiss_suggestion,
    get_suggestions_for_game,
    get_suggestions_for_tournament,
)
from steam.functions.league_sync import (
    link_user_to_stats,
    relink_all_users,
    retry_failed_matches,
    sync_league_matches,
)
from steam.functions.match_utils import find_matches_by_players
from steam.models import LeagueSyncState, Match, PlayerMatchStats
from steam.serializers import (
    AutoLinkRequestSerializer,
    AutoLinkResultSerializer,
    FindMatchesByPlayersSerializer,
    GameMatchSuggestionSerializer,
    LinkMatchRequestSerializer,
    MatchSerializer,
    RelinkUsersSerializer,
    RetryFailedRequestSerializer,
    SyncLeagueRequestSerializer,
    SyncResultSerializer,
    SyncStatusSerializer,
)
from steam.services.match_suggestions import get_match_suggestions_for_game
from steam.utils.steam_api_caller import SteamAPI

log = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def sync_league(request):
    """Trigger league sync (full or incremental)."""
    serializer = SyncLeagueRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    league_id = serializer.validated_data["league_id"]
    full_sync = serializer.validated_data["full_sync"]

    result = sync_league_matches(league_id, full_sync=full_sync)

    return Response(SyncResultSerializer(result).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def retry_failed(request):
    """Retry failed match fetches."""
    serializer = RetryFailedRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    league_id = serializer.validated_data["league_id"]
    result = retry_failed_matches(league_id)

    return Response(SyncResultSerializer(result).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def relink_users(request):
    """Re-link users to match stats."""
    serializer = RelinkUsersSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    match_ids = serializer.validated_data.get("match_ids", [])

    if match_ids:
        # Relink specific matches
        linked_count = 0
        for match_id in match_ids:
            stats = PlayerMatchStats.objects.filter(
                match__match_id=match_id, user__isnull=True
            )
            for stat in stats:
                if link_user_to_stats(stat):
                    linked_count += 1
        result = {"linked_count": linked_count}
    else:
        # Relink all
        linked_count = relink_all_users()
        result = {"linked_count": linked_count}

    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
def find_by_players(request):
    """Find matches by player steam IDs."""
    serializer = FindMatchesByPlayersSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    steam_ids = serializer.validated_data["steam_ids"]
    require_all = serializer.validated_data["require_all"]
    league_id = serializer.validated_data.get("league_id")

    matches = find_matches_by_players(
        steam_ids, require_all=require_all, league_id=league_id
    )

    return Response(MatchSerializer(matches, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_live_games(request):
    """Get live league games."""
    league_id = request.query_params.get("league_id", LEAGUE_ID)

    try:
        league_id = int(league_id)
    except (TypeError, ValueError):
        league_id = LEAGUE_ID

    api = SteamAPI()
    result = api.get_live_league_games(league_id=league_id)

    if result and "result" in result:
        return Response(result["result"])

    return Response({"games": []})


@api_view(["GET"])
@permission_classes([AllowAny])
def get_sync_status(request):
    """Get current sync state."""
    league_id = request.query_params.get("league_id", LEAGUE_ID)

    try:
        league_id = int(league_id)
    except (TypeError, ValueError):
        league_id = LEAGUE_ID

    try:
        state = LeagueSyncState.objects.get(league_id=league_id)
        data = {
            "league_id": state.league_id,
            "last_sync_at": state.last_sync_at,
            "last_match_id": state.last_match_id,
            "failed_match_count": len(state.failed_match_ids),
            "is_syncing": state.is_syncing,
        }
    except LeagueSyncState.DoesNotExist:
        data = {
            "league_id": league_id,
            "last_sync_at": None,
            "last_match_id": None,
            "failed_match_count": 0,
            "is_syncing": False,
        }

    return Response(SyncStatusSerializer(data).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def auto_link_tournament(request):
    """Trigger auto-linking for a tournament."""
    serializer = AutoLinkRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    tournament_id = serializer.validated_data["tournament_id"]
    result = auto_link_matches_for_tournament(tournament_id)

    return Response(AutoLinkResultSerializer(result).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_tournament_suggestions(request, tournament_id):
    """Get match suggestions for a tournament."""
    suggestions = get_suggestions_for_tournament(tournament_id)
    return Response(GameMatchSuggestionSerializer(suggestions, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_game_suggestions(request, game_id):
    """Get match suggestions for a specific game."""
    suggestions = get_suggestions_for_game(game_id)
    return Response(GameMatchSuggestionSerializer(suggestions, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def confirm_match_suggestion(request, suggestion_id):
    """Confirm a suggestion (link game to match)."""
    success = confirm_suggestion(suggestion_id)

    if success:
        return Response({"status": "confirmed"})
    else:
        return Response(
            {"error": "Suggestion not found or game already linked"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def dismiss_match_suggestion(request, suggestion_id):
    """Dismiss a suggestion."""
    success = dismiss_suggestion(suggestion_id)

    if success:
        return Response({"status": "dismissed"})
    else:
        return Response(
            {"error": "Suggestion not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_game_match_suggestions(request, game_id):
    """
    Get match suggestions for a bracket game with captain-aware tiers.

    Query params:
    - search: Filter by match ID or captain name
    """
    from app.models import Game

    try:
        game = (
            Game.objects.select_related(
                "tournament",
                "radiant_team__captain",
                "dire_team__captain",
            )
            .prefetch_related(
                "radiant_team__members",
                "dire_team__members",
            )
            .get(pk=game_id)
        )
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    search = request.query_params.get("search", None)
    suggestions = get_match_suggestions_for_game(game, search=search)

    return Response(
        {
            "suggestions": suggestions,
            "linked_match_id": game.gameid,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_game_match(request, game_id):
    """Link a bracket game to a Steam match.

    Requires league staff access.
    """
    from cacheops import invalidate_obj

    from app.models import Game

    serializer = LinkMatchRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    match_id = serializer.validated_data["match_id"]

    try:
        game = Game.objects.select_related("tournament", "league").get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check permission
    if not can_manage_game(request.user, game):
        return Response(
            {"error": "You do not have permission to link matches for this game"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Verify match exists
    if not Match.objects.filter(match_id=match_id).exists():
        return Response(
            {"error": "Match not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    game.gameid = match_id
    game.save()

    # Invalidate cache for game and tournament
    invalidate_obj(game)
    if game.tournament:
        invalidate_obj(game.tournament)

    return Response({"status": "linked", "match_id": match_id})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def unlink_game_match(request, game_id):
    """Unlink a bracket game from its Steam match.

    Requires league staff access.
    """
    from cacheops import invalidate_obj

    from app.models import Game

    try:
        game = Game.objects.select_related("tournament", "league").get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": "Game not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check permission
    if not can_manage_game(request.user, game):
        return Response(
            {"error": "You do not have permission to unlink matches for this game"},
            status=status.HTTP_403_FORBIDDEN,
        )

    game.gameid = None
    game.winning_team = None
    game.status = "scheduled"
    game.save(update_fields=["gameid", "winning_team", "status"])

    # Invalidate cache for game and tournament
    invalidate_obj(game)
    if game.tournament:
        invalidate_obj(game.tournament)

    return Response({"status": "unlinked"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_assign_matches(request):
    """
    Auto-assign Steam matches to tournament bracket games based on time order.

    Uses tournament date_played to filter matches to that day only,
    then assigns matches to games based on bracket order (winners first,
    then losers, sorted by round/position) and player overlap.

    Requires league staff access.

    Body params:
    - tournament_id: Tournament to auto-assign matches for
    - preview: If true (default), returns assignments without applying them
    - min_overlap: Minimum player overlap required (default 4)
    - apply: If true, applies the assignments (overrides preview)
    """
    from app.models import Tournament
    from app.permissions_org import has_league_staff_access

    tournament_id = request.data.get("tournament_id")
    if not tournament_id:
        return Response(
            {"error": "tournament_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check permission
    try:
        tournament = Tournament.objects.select_related("league").get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if tournament.league and not has_league_staff_access(
        request.user, tournament.league
    ):
        return Response(
            {
                "error": "You do not have permission to auto-assign matches for this tournament"
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    preview = request.data.get("preview", True)
    apply_assignments = request.data.get("apply", False)
    min_overlap = request.data.get("min_overlap", 4)

    # apply=True overrides preview
    if apply_assignments:
        preview = False

    try:
        min_overlap = int(min_overlap)
    except (TypeError, ValueError):
        min_overlap = 4

    result = auto_assign_matches_by_time(
        tournament_id=tournament_id,
        preview=preview,
        min_overlap=min_overlap,
    )

    return Response(result)
