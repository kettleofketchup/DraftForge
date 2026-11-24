"""Lightweight read-only views for SSR meta tags.

These endpoints are public (no auth required) and return minimal data
for server-side rendering of meta tags and above-the-fold content.
"""

from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from app.serializers_ssr import EventSerializerSSR
from events.models import Event


class EventSSRView(RetrieveAPIView):
    serializer_class = EventSerializerSSR
    permission_classes = [AllowAny]
    queryset = Event.objects.select_related("organization", "tournament_league")
