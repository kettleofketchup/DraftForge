"""
WebSocket URL routing for draft events.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("api/draft/<int:draft_id>/", consumers.DraftConsumer.as_asgi()),
    path("api/tournament/<int:tournament_id>/", consumers.TournamentConsumer.as_asgi()),
    path("api/herodraft/<int:draft_id>/", consumers.HeroDraftConsumer.as_asgi()),
]
