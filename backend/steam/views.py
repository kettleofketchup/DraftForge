from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .functions.match import update_match_details
from .models import Match
from .serializers import MatchSerializer


class MatchDetailView(APIView):
    """
    API view to get details of a specific match.
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
