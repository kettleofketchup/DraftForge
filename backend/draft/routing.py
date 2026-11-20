"""Hero draft WebSocket routes; composed with app.routing in backend/asgi.py."""

from django.urls import URLPattern, path

from discordbot.activity_auth import ActivitySocketMiddleware
from draft.consumers.hero import HeroDraftConsumer

websocket_urlpatterns: list[URLPattern] = [
    path(
        "api/discord/activity/draft/<int:draft_id>/",
        ActivitySocketMiddleware(HeroDraftConsumer.as_asgi(), "hero"),
    ),
    path("api/herodraft/<int:draft_id>/", HeroDraftConsumer.as_asgi()),
]
