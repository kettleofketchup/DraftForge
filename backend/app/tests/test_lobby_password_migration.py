import importlib
import unittest

from django.conf import settings
from django.test import override_settings

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

lobby_0004 = importlib.import_module("lobby.migrations.0004_gamelobby_password")


class GameLobbyPasswordMigrationTest(MigratorTestCase):
    """lobby 0004: lobbies keep the password they were created with."""

    migrate_from = [
        ("app", "0096_squashed_0106"),
        ("lobby", "0003_gamelobby_close_pending"),
    ]
    migrate_to = ("lobby", "0004_gamelobby_password")

    def prepare(self):
        apps = self.old_state.apps
        Tournament = apps.get_model("app", "Tournament")
        Game = apps.get_model("app", "Game")
        GameLobby = apps.get_model("lobby", "GameLobby")

        tournament = Tournament.objects.create(
            name="On", date_played="2026-11-20T18:00:00Z", dota_lobby_mode="auto"
        )
        Tournament.objects.filter(pk=tournament.pk).update(
            dota_lobby_password="tournament-pw"
        )
        game = Game.objects.create(tournament=tournament)
        other_game = Game.objects.create(tournament=tournament)
        current_key = lobby_0004._key_id(settings.SECRET_KEY)
        derived = GameLobby.objects.create(
            game=game, external_ref=f"game:{game.pk}", password_key_id=current_key
        )
        ended = GameLobby.objects.create(
            game=game,
            external_ref=f"game:{game.pk}",
            state="closed",
            ended=True,
            password_key_id=current_key,
        )
        key_gone = GameLobby.objects.create(
            game=other_game,
            external_ref=f"game:{other_game.pk}",
            password_key_id="0123456789abcdef",
        )
        self.pks = {"derived": derived.pk, "ended": ended.pk, "key_gone": key_gone.pk}
        self.expected_derived = lobby_0004._derived(derived, settings.SECRET_KEY)

    def test_passwords(self):
        GameLobby = self.new_state.apps.get_model("lobby", "GameLobby")
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["derived"]).password,
            self.expected_derived,
        )
        self.assertEqual(GameLobby.objects.get(pk=self.pks["ended"]).password, "")
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["key_gone"]).password, "tournament-pw"
        )
        self.assertNotIn(
            "password_key_id", {f.name for f in GameLobby._meta.get_fields()}
        )


OLD_KEY = "an-old-secret-key-still-in-the-fallbacks-0123456789"


@override_settings(SECRET_KEY_FALLBACKS=[OLD_KEY])
class GameLobbyPasswordRollbackTest(MigratorTestCase):
    """lobby 0004 reversed: each lobby names the key its password derives under."""

    migrate_from = ("lobby", "0004_gamelobby_password")
    migrate_to = ("lobby", "0003_gamelobby_close_pending")

    def prepare(self):
        apps = self.old_state.apps
        Tournament = apps.get_model("app", "Tournament")
        Game = apps.get_model("app", "Game")
        GameLobby = apps.get_model("lobby", "GameLobby")
        tournament = Tournament.objects.create(
            name="On", date_played="2026-11-20T18:00:00Z", dota_lobby_mode="auto"
        )
        game = Game.objects.create(tournament=tournament)

        def lobby(**fields):
            return GameLobby.objects.create(
                game=game, external_ref=f"game:{game.pk}", ended=True, **fields
            )

        current = lobby()
        GameLobby.objects.filter(pk=current.pk).update(
            password=lobby_0004._derived(current, settings.SECRET_KEY)
        )
        old = lobby()
        GameLobby.objects.filter(pk=old.pk).update(
            password=lobby_0004._derived(old, OLD_KEY)
        )
        shared = lobby(password="tournament-pw")
        self.pks = {"current": current.pk, "old": old.pk, "shared": shared.pk}

    def test_key_ids(self):
        GameLobby = self.new_state.apps.get_model("lobby", "GameLobby")
        current_key = lobby_0004._key_id(settings.SECRET_KEY)
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["current"]).password_key_id, current_key
        )
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["old"]).password_key_id,
            lobby_0004._key_id(OLD_KEY),
        )
        # Its stored password cannot be derived: it falls back to the current key.
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["shared"]).password_key_id, current_key
        )
