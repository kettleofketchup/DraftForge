from django.conf import settings
from django.http import QueryDict
from rest_framework import generics, status
from rest_framework.generics import RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.models import League
from user.querysets import with_user_profiles

from .constants import LEAGUE_ID
from .functions.league_summary import empty_league_summary, get_league_summary
from .functions.match import update_match_details
from .models import LeaguePlayerStats, Match
from .serializers import (
    LeaderboardSerializer,
    LeaguePlayerStatsSerializer,
    MatchDetailSerializer,
    MatchSerializer,
)


class MatchDetailView(APIView):
    """
    API view to get details of a specific match.
    Fetches from Steam API if not cached locally.
    """

    def get(self, request, match_id):
        match = update_match_details(match_id)
        if match:
            serializer = MatchSerializer(match)
            return Response(serializer.data)
        return Response(
            {"error": "Failed to fetch match details"},
            status=status.HTTP_404_NOT_FOUND,
        )


class MatchRetrieveView(RetrieveAPIView):
    """
    API view to retrieve match details from the database.
    Returns match data with nested player stats.
    """

    queryset = Match.objects.prefetch_related("players__user")
    serializer_class = MatchDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "match_id"


class LeaderboardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LeaderboardView(generics.ListAPIView):
    """
    GET /api/steam/leaderboard/
    Returns paginated leaderboard sorted by league_mmr.

    Query params:
    - sort_by: league_mmr, win_rate, games_played, avg_kda (default: league_mmr)
    - order: desc, asc (default: desc)
    - page: page number
    - page_size: items per page (default: 20, max: 100)
    """

    serializer_class = LeaderboardSerializer
    pagination_class = LeaderboardPagination

    def get_queryset(self):
        # LeaguePlayerStatsSerializer ships user.avatar via source="user.avatar",
        # which goes through CustomUser.avatar @property → base_profile.avatar
        # (T1 epic). Paginated up to 100; without user__base_profile, the
        # leaderboard is N+1 cold-cache.
        queryset = with_user_profiles(
            LeaguePlayerStats.objects.filter(
                league_id=LEAGUE_ID,
                games_played__gt=0,
                user__isnull=False,
            ),
            "user",
        )

        # Sorting
        sort_by = self.request.query_params.get("sort_by", "league_mmr")
        order = self.request.query_params.get("order", "desc")

        sort_fields = {
            "league_mmr": "user__league_mmr",
            "win_rate": "win_rate",
            "games_played": "games_played",
            "avg_kda": "avg_kills",  # Approximate sort
        }

        sort_field = sort_fields.get(sort_by, "user__league_mmr")
        if order == "desc":
            sort_field = f"-{sort_field}"

        return queryset.order_by(sort_field)


def _resolve_stats_league_id(params: QueryDict) -> int | Response:
    if "league" in params:
        try:
            league_pk = int(params["league"])
        except ValueError:
            return Response(
                {"error": "Invalid league"}, status=status.HTTP_400_BAD_REQUEST
            )
        steam_league_id = (
            League.objects.filter(pk=league_pk)
            .values_list("steam_league_id", flat=True)
            .first()
        )
        if steam_league_id is None:
            return Response(
                {"error": "League not found"}, status=status.HTTP_404_NOT_FOUND
            )
        return steam_league_id
    if "league_id" in params:
        try:
            return int(params["league_id"])
        except ValueError:
            return Response(
                {"error": "Invalid league_id"}, status=status.HTTP_400_BAD_REQUEST
            )
    return LEAGUE_ID


class LeagueStatsView(APIView):
    """
    GET /api/steam/league-stats/<user_id>/
    Returns a user's league stats.
    """

    def get(self, request: Request, user_id: int) -> Response:
        league_id = _resolve_stats_league_id(request.query_params)
        if isinstance(league_id, Response):
            return league_id
        try:
            stats = LeaguePlayerStats.objects.select_related("user").get(
                user_id=user_id,
                league_id=league_id,
            )
            serializer = LeaguePlayerStatsSerializer(stats)
            return Response(serializer.data)
        except LeaguePlayerStats.DoesNotExist:
            return Response(
                {"error": "No league stats found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )


class MyLeagueStatsView(APIView):
    """
    GET /api/steam/league-stats/me/
    Returns the authenticated user's league stats.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            stats = LeaguePlayerStats.objects.select_related("user").get(
                user=request.user,
                league_id=LEAGUE_ID,
            )
            serializer = LeaguePlayerStatsSerializer(stats)
            return Response(serializer.data)
        except LeaguePlayerStats.DoesNotExist:
            return Response(
                {"error": "No league stats found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class LeaguePlayerSummariesView(APIView):
    """
    GET /api/steam/leagues/<league_pk>/player-summaries/
    Returns per-player ticket-match summaries and the win-rate distribution
    for a DraftForge league.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, league_pk: int) -> Response:
        league = League.objects.filter(pk=league_pk).values("steam_league_id").first()
        if league is None:
            return Response(
                {"error": "League not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        steam_league_id: int | None = league["steam_league_id"]
        min_games: int = settings.LEAGUE_MMR_MIN_GAMES
        summary = (
            empty_league_summary(min_games)
            if steam_league_id is None
            else get_league_summary(steam_league_id, min_games)
        )
        return Response(
            {"league_pk": league_pk, "steam_league_id": steam_league_id, **summary}
        )
