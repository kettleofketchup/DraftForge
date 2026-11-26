"""Views for joke-related endpoints (tangoes, etc.)."""

from django.db.models import F
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from joke.models import Joke
from joke.serializers import JokeSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_tangoes(request: Request) -> Response:
    """Get current user's tango count."""
    joke, _ = Joke.objects.get_or_create(user=request.user)
    serializer = JokeSerializer(joke)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buy_tango(request: Request) -> Response:
    """Increment user's tango count by 1."""
    joke, _ = Joke.objects.get_or_create(user=request.user)
    Joke.objects.filter(pk=joke.pk).update(
        tangoes_purchased=F("tangoes_purchased") + 1, updated_at=timezone.now()
    )
    joke.refresh_from_db(fields=["tangoes_purchased"])

    return Response(
        {
            "tangoes_purchased": joke.tangoes_purchased,
            "message": "You bought a tango! 🌿",
        },
        status=status.HTTP_200_OK,
    )
