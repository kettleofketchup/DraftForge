import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from app.models import Game
from lobby.models import GameLobby
from lobby.passwords import (
    PASSWORD_LENGTH,
    PasswordKeyUnavailable,
    current_key_id,
    derive_password,
    key_id,
)

OLD_KEY = "dummy-old-secret-key-for-lobby-password-tests"
NEW_KEY = "dummy-new-secret-key-for-lobby-password-tests"


class DerivePasswordTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create()
        self.lobby = GameLobby.objects.create(
            game=self.game, external_ref=f"game:{self.game.pk}"
        )

    def _end(self, lobby, state=GameLobby.State.ERROR):
        lobby.state = state
        lobby.save()

    def _recreate(self):
        return GameLobby.objects.create(
            game=self.game, external_ref=self.lobby.external_ref
        )

    def test_deterministic(self):
        again = GameLobby.objects.get(pk=self.lobby.pk)
        self.assertEqual(derive_password(self.lobby), derive_password(again))

    def test_length_and_charset(self):
        password = derive_password(self.lobby)
        self.assertEqual(len(password), PASSWORD_LENGTH)
        self.assertRegex(password, re.compile(r"^[a-z2-7]{12}$"))

    def test_records_current_key(self):
        self.assertEqual(self.lobby.password_key_id, current_key_id())
        self.assertNotIn(settings.SECRET_KEY, self.lobby.password_key_id)

    def test_same_for_a_recreated_lobby(self):
        # After an ambiguous failure dota_lobby may still hold the first
        # lobby; the new row must send the same body so it is a replay (200),
        # not a 409 conflict.
        self._end(self.lobby)
        second = self._recreate()
        self.assertNotEqual(second.pk, self.lobby.pk)
        self.assertEqual(derive_password(second), derive_password(self.lobby))

    def test_differs_per_game(self):
        other_game = Game.objects.create()
        other = GameLobby.objects.create(
            game=other_game, external_ref=f"game:{other_game.pk}"
        )
        self.assertNotEqual(derive_password(other), derive_password(self.lobby))

    def test_differs_per_ref_prefix(self):
        staging = GameLobby.objects.create(
            game=Game.objects.create(), external_ref=f"staging:{self.game.pk}"
        )
        self.assertNotEqual(derive_password(staging), derive_password(self.lobby))

    def test_survives_secret_key_rotation(self):
        with override_settings(SECRET_KEY=OLD_KEY):
            before = derive_password(self.lobby_under_old_key())
        with override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[OLD_KEY]):
            lobby = GameLobby.objects.get(pk=self.old_lobby.pk)
            self.assertEqual(derive_password(lobby), before)
            # A lobby recreated for that game keeps the old key's password.
            self._end(lobby)
            again = GameLobby.objects.create(
                game=self.old_game, external_ref=lobby.external_ref
            )
            self.assertEqual(again.password_key_id, key_id(OLD_KEY))
            self.assertEqual(derive_password(again), before)
            # A new game uses the new key.
            fresh = GameLobby.objects.create(
                game=Game.objects.create(), external_ref="game:fresh"
            )
            self.assertEqual(fresh.password_key_id, key_id(NEW_KEY))

    def test_dropped_key_refused(self):
        with override_settings(SECRET_KEY=OLD_KEY):
            before = derive_password(self.lobby_under_old_key())
        with override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[]):
            lobby = GameLobby.objects.get(pk=self.old_lobby.pk)
            with self.assertRaises(PasswordKeyUnavailable):
                derive_password(lobby)
            # A recreated lobby falls back to the current key.
            self._end(lobby)
            again = GameLobby.objects.create(
                game=self.old_game, external_ref=lobby.external_ref
            )
            self.assertEqual(again.password_key_id, key_id(NEW_KEY))
            self.assertNotEqual(derive_password(again), before)

    def lobby_under_old_key(self):
        self.old_game = Game.objects.create()
        self.old_lobby = GameLobby.objects.create(
            game=self.old_game, external_ref=f"game:{self.old_game.pk}"
        )
        self.assertEqual(self.old_lobby.password_key_id, key_id(OLD_KEY))
        return self.old_lobby

    def test_public_dev_key_refused_in_production(self):
        dev_key = settings.INSECURE_DEV_SECRET_KEY
        with override_settings(SECRET_KEY=dev_key):
            game = Game.objects.create()
            lobby = GameLobby.objects.create(game=game, external_ref="game:dev")
            derive_password(lobby)  # allowed under tests
            with (
                override_settings(DEBUG=False, TEST=False, RUNNING_TESTS=False),
                self.assertRaises(ImproperlyConfigured),
            ):
                derive_password(lobby)
            with override_settings(DEBUG=True, TEST=False, RUNNING_TESTS=False):
                derive_password(lobby)

    def test_unsaved_row_refused(self):
        with self.assertRaises(ValueError):
            derive_password(GameLobby(game=self.game, external_ref="game:1"))
