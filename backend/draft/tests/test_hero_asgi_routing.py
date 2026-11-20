from typing import Any

from channels.routing import URLRouter
from django.test import SimpleTestCase

from backend import asgi
from discordbot.activity_auth import ActivitySocketMiddleware
from draft.consumers.hero import HeroDraftConsumer


def _websocket_router() -> URLRouter:
    app: Any = asgi.application.application_mapping["websocket"]
    while not isinstance(app, URLRouter):
        app = getattr(app, "inner", None) or app.application
    return app


def _resolve(path: str) -> Any:
    for route in _websocket_router().routes:
        if route.pattern.match(path):
            return route.callback
    return None


class HeroAsgiRoutingTests(SimpleTestCase):
    def test_herodraft_socket_routes_to_moved_consumer(self) -> None:
        callback = _resolve("api/herodraft/1/")
        self.assertIsNotNone(callback)
        self.assertIs(callback.consumer_class, HeroDraftConsumer)

    def test_activity_hero_socket_is_wrapped_hero_consumer(self) -> None:
        callback = _resolve("api/discord/activity/draft/1/")
        self.assertIsInstance(callback, ActivitySocketMiddleware)
        self.assertEqual(callback.kind, "hero")
        self.assertIs(callback.app.consumer_class, HeroDraftConsumer)

    def test_team_and_tournament_sockets_still_routed(self) -> None:
        for path in (
            "api/draft/1/",
            "api/tournament/1/",
            "api/discord/activity/team-draft/1/",
        ):
            self.assertIsNotNone(_resolve(path), path)
