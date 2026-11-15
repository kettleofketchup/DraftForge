"""
WebSocket URL routing for draft events.
"""

from django.urls import path

from discordbot.activity_auth import ActivitySocketMiddleware

from . import consumers

websocket_urlpatterns = [
    path(
        "api/discord/activity/team-draft/<int:draft_id>/",
        ActivitySocketMiddleware(consumers.DraftConsumer.as_asgi(), "team"),
    ),
    path(
        "api/discord/activity/draft/<int:draft_id>/",
        ActivitySocketMiddleware(consumers.HeroDraftConsumer.as_asgi(), "hero"),
    ),
    path("api/draft/<int:draft_id>/", consumers.DraftConsumer.as_asgi()),
    path("api/tournament/<int:tournament_id>/", consumers.TournamentConsumer.as_asgi()),
    path("api/herodraft/<int:draft_id>/", consumers.HeroDraftConsumer.as_asgi()),
]
