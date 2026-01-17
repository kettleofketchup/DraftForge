"""
WebSocket URL routing for draft events.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/draft/<int:draft_id>/", consumers.DraftConsumer.as_asgi()),
    path("ws/tournament/<int:tournament_id>/", consumers.TournamentConsumer.as_asgi()),
]
