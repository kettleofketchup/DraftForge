import re

from django.test import TestCase, override_settings

from app.models import Game
from lobby.models import GameLobby
from lobby.passwords import PASSWORD_LENGTH, derive_password


class DerivePasswordTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create()
        self.lobby = GameLobby.objects.create(
            game=self.game, external_ref=f"game:{self.game.pk}"
        )

    def test_deterministic(self):
        again = GameLobby.objects.get(pk=self.lobby.pk)
        self.assertEqual(derive_password(self.lobby), derive_password(again))

    def test_length_and_charset(self):
        password = derive_password(self.lobby)
        self.assertEqual(len(password), PASSWORD_LENGTH)
        self.assertRegex(password, re.compile(r"^[a-z2-7]{12}$"))

    def test_differs_per_row(self):
        self.lobby.state = GameLobby.State.CLOSED
        self.lobby.save()
        second = GameLobby.objects.create(
            game=self.game, external_ref=self.lobby.external_ref
        )
        self.assertNotEqual(derive_password(self.lobby), derive_password(second))

    def test_depends_on_secret_key(self):
        before = derive_password(self.lobby)
        with override_settings(SECRET_KEY="another-dummy-secret-key"):
            self.assertNotEqual(derive_password(self.lobby), before)

    def test_unsaved_row_refused(self):
        with self.assertRaises(ValueError):
            derive_password(GameLobby(game=self.game, external_ref="game:1"))
