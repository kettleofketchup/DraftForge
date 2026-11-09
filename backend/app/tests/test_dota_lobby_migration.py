import unittest

from django.db import connection

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class TournamentDotaLobbyFieldsMigrationTest(MigratorTestCase):
    """0097 widens Game.gameid and adds the off-by-default lobby fields."""

    migrate_from = ("app", "0096_drop_customuser_positions_dota_mmr")
    migrate_to = ("app", "0097_tournament_dota_lobby_fields")

    def prepare(self):
        Tournament = self.old_state.apps.get_model("app", "Tournament")
        Game = self.old_state.apps.get_model("app", "Game")
        tournament = Tournament.objects.create(
            name="Before 0097", date_played="2026-11-01T18:00:00Z"
        )
        self.tournament_pk = tournament.pk
        self.linked = Game.objects.create(tournament=tournament, gameid=8012345678)
        self.unlinked = Game.objects.create(tournament=tournament)

    def test_existing_rows_kept(self):
        Tournament = self.new_state.apps.get_model("app", "Tournament")
        Game = self.new_state.apps.get_model("app", "Game")

        tournament = Tournament.objects.get(pk=self.tournament_pk)
        self.assertEqual(tournament.dota_lobby_mode, "off")
        self.assertEqual(tournament.dota_lobby_launch, "manual")
        self.assertEqual(tournament.dota_lobby_region, "")
        self.assertFalse(tournament.discord_send_lobby_info)

        self.assertEqual(Game.objects.get(pk=self.linked.pk).gameid, 8012345678)
        self.assertIsNone(Game.objects.get(pk=self.unlinked.pk).gameid)

        Game.objects.create(tournament=tournament, gameid=2**62)
        self.assertTrue(Game.objects.filter(gameid=2**62).exists())

    def test_gameid_has_one_index(self):
        # Game.Meta.indexes already indexes gameid; widening must not add a
        # second, field-level index.
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "app_game")
        gameid_indexes = [
            name
            for name, info in constraints.items()
            if info["index"] and info["columns"] == ["gameid"]
        ]
        self.assertEqual(len(gameid_indexes), 1, gameid_indexes)
