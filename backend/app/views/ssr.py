"""Lightweight read-only views for SSR meta tags.

These endpoints are public (no auth required) and return minimal data
for server-side rendering of meta tags and above-the-fold content.
"""

from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from app.models import CustomUser, League, Tournament
from app.serializers_ssr import (
    EventSerializerSSR,
    LeagueSerializerSSR,
    TournamentSerializerSSR,
    UserSerializerSSR,
)
from events.models import Event


class TournamentSSRView(RetrieveAPIView):
    serializer_class = TournamentSerializerSSR
    permission_classes = [AllowAny]
    queryset = Tournament.objects.select_related("league__organization")


class LeagueSSRView(RetrieveAPIView):
    serializer_class = LeagueSerializerSSR
    permission_classes = [AllowAny]
    queryset = League.objects.select_related("organization")


class EventSSRView(RetrieveAPIView):
    serializer_class = EventSerializerSSR
    permission_classes = [AllowAny]
    queryset = Event.objects.select_related("organization", "tournament_league")


class UserSSRView(RetrieveAPIView):
    serializer_class = UserSerializerSSR
    permission_classes = [AllowAny]
    queryset = CustomUser.objects.all()
