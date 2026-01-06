from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .functions.match import update_match_details
from .models import Match
from .serializers import MatchDetailSerializer, MatchSerializer


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
