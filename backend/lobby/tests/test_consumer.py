import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings

from app.models import Tournament
from lobby import broadcast
from lobby.models import GameLobby
from lobby.tests.helpers import make_game


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class TournamentSocketLobbyTests(TransactionTestCase):
    def test_lobby_event_and_bracket_update_reach_clients(self):
        from channels.routing import URLRouter
        from django.urls import path

        from app.consumers import TournamentConsumer

        application = URLRouter(
            [path("api/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi())]
        )

        game = make_game()
        row = GameLobby.objects.create(
            game=game,
            external_ref=f"game:{game.pk}",
            lobby_id="lob_1",
            state="in_game",
            match_id=8123456789,
        )
        tournament_id = game.tournament_id

        async def scenario():
            comm = WebsocketCommunicator(
                application, f"/api/tournament/{tournament_id}/"
            )
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.receive_json_from()  # initial_events
            layer = get_channel_layer()
            for message in (
                broadcast.lobby_message(row),
                {"type": "bracket.update", "game_id": game.pk},
            ):
                await layer.group_send(f"tournament_{tournament_id}", message)
            first = await comm.receive_json_from()
            second = await comm.receive_json_from()
            await comm.disconnect()
            return first, second

        first, second = async_to_sync(scenario)()
        self.assertEqual(
            first,
            {
                "type": "lobby_event",
                "game_id": game.pk,
                "game_lobby_id": row.pk,
                "state": "in_game",
                "match_id": "8123456789",
                "provisional_winner_side": None,
            },
        )
        self.assertEqual(second, {"type": "bracket_update", "game_id": game.pk})
        self.assertTrue(Tournament.objects.filter(pk=tournament_id).exists())
        self.assertNotIn("password", json.dumps(first))
