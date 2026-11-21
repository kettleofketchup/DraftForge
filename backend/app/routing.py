"""Tournament WebSocket route; composed with draft.routing in backend/asgi.py."""

from django.urls import URLPattern, path

from app.consumers import TournamentConsumer

websocket_urlpatterns: list[URLPattern] = [
    path("api/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi()),
]
