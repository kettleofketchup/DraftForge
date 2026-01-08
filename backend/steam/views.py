from rest_framework import generics, status
from rest_framework.generics import RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import LEAGUE_ID
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
        queryset = LeaguePlayerStats.objects.filter(
            league_id=LEAGUE_ID,
            games_played__gt=0,
            user__isnull=False,
        ).select_related("user")

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


class LeagueStatsView(APIView):
    """
    GET /api/steam/league-stats/<user_id>/
    Returns a user's league stats.
    """

    def get(self, request, user_id):
        try:
            stats = LeaguePlayerStats.objects.select_related("user").get(
                user_id=user_id,
                league_id=LEAGUE_ID,
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
