"""Views for joke-related endpoints (tangoes, etc.)."""

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
    joke.tangoes_purchased += 1
    joke.save()

    return Response(
        {
            "tangoes_purchased": joke.tangoes_purchased,
            "message": "You bought a tango! 🌿",
        },
        status=status.HTTP_200_OK,
    )
