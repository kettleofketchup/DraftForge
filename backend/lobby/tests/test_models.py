from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from app.models import DotaLobbyLaunch, DotaLobbyMode, Game, Tournament
from lobby.models import GameLobby, GameLobbyEvent
from lobby.states import ENDED_STATES


class GameLobbyTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create()
        self.ref = f"game:{self.game.pk}"

    def _lobby(self, **kwargs):
        return GameLobby.objects.create(game=self.game, external_ref=self.ref, **kwargs)

    def test_defaults(self):
        lobby = self._lobby()
        self.assertEqual(lobby.state, GameLobby.State.REQUESTED)
        self.assertFalse(lobby.ended)
        self.assertIsNone(lobby.ended_at)
        self.assertIsNone(lobby.lobby_id)
        self.assertEqual(
            (lobby.request, lobby.players, lobby.pending_invites), ({}, {}, [])
        )
        self.assertEqual(list(self.game.lobbies.all()), [lobby])

    def test_one_active_lobby_per_game(self):
        self._lobby()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._lobby()

    def test_ended_lobbies_keep_history(self):
        first = self._lobby(lobby_id="lob_a")
        first.state = GameLobby.State.TIMED_OUT
        first.save(update_fields=["state"])
        first.refresh_from_db()
        self.assertTrue(first.ended)
        self.assertIsNotNone(first.ended_at)

        second = self._lobby(lobby_id="lob_b")
        self.assertFalse(second.ended)
        self.assertEqual(self.game.lobbies.count(), 2)
        self.assertEqual(self.game.lobbies.filter(ended=False).get(), second)

    def test_ended_follows_state(self):
        for state in GameLobby.State.values:
            with self.subTest(state=state):
                lobby = GameLobby(game=self.game, external_ref=self.ref, state=state)
                lobby.save()
                self.assertEqual(lobby.ended, state in ENDED_STATES)
                lobby.delete()

    def test_lobby_id_unique(self):
        self._lobby(lobby_id="lob_a", state=GameLobby.State.CLOSED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._lobby(lobby_id="lob_a")

    def test_unaccepted_lobbies_may_share_null_lobby_id(self):
        self._lobby(state=GameLobby.State.ERROR)
        self._lobby()
        self.assertEqual(self.game.lobbies.filter(lobby_id__isnull=True).count(), 2)

    def test_deleting_game_deletes_lobbies(self):
        self._lobby()
        self.game.delete()
        self.assertFalse(GameLobby.objects.exists())


class GameLobbyEventTests(TestCase):
    def setUp(self):
        game = Game.objects.create()
        self.lobby = GameLobby.objects.create(game=game, external_ref=f"game:{game.pk}")

    def _event(self, event_id, seq):
        return GameLobbyEvent.objects.create(
            event_id=event_id,
            lobby=self.lobby,
            seq=seq,
            type="lobby.state_changed",
            occurred_at="2026-11-09T12:00:00Z",
            payload={"id": event_id},
            source=GameLobbyEvent.Source.WEBHOOK,
        )

    def test_seq_unique_per_lobby(self):
        self._event("evt_1", 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._event("evt_2", 1)

    def test_event_id_is_the_key(self):
        self._event("evt_1", 1)
        self.assertEqual(GameLobbyEvent.objects.get(pk="evt_1").seq, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._event("evt_1", 2)

    def test_ordered_by_seq(self):
        self._event("evt_b", 2)
        self._event("evt_a", 1)
        self.assertEqual([e.seq for e in self.lobby.events.all()], [1, 2])


class TournamentLobbyFieldTests(TestCase):
    def test_defaults_keep_lobbies_off(self):
        tournament = Tournament.objects.create(
            name="Lobby defaults", date_played=timezone.now()
        )
        self.assertEqual(tournament.dota_lobby_mode, DotaLobbyMode.OFF)
        self.assertEqual(tournament.dota_lobby_launch, DotaLobbyLaunch.MANUAL)
        self.assertEqual(tournament.dota_lobby_region, "")
        self.assertFalse(tournament.discord_send_lobby_info)

    def test_gameid_holds_a_64_bit_match_id(self):
        match_id = 8_123_456_789_012
        game = Game.objects.create(gameid=match_id)
        game.refresh_from_db()
        self.assertEqual(game.gameid, match_id)
