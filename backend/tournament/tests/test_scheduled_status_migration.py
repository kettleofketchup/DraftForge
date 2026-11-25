from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from tournament.models import Game, Tournament

migration = import_module("tournament.migrations.0003_game_scheduled_status_to_pending")


class ScheduledStatusMigrationTests(TestCase):
    def test_scheduled_games_become_pending_and_others_are_untouched(self) -> None:
        tournament = Tournament.objects.create(
            name="Scheduled Repair Cup", date_played=timezone.now()
        )
        stuck = Game.objects.create(tournament=tournament)
        live = Game.objects.create(tournament=tournament, status="live")
        Game.objects.filter(pk=stuck.pk).update(status="scheduled")

        migration.scheduled_games_to_pending(apps, None)

        self.assertEqual(Game.objects.nocache().get(pk=stuck.pk).status, "pending")
        self.assertEqual(Game.objects.nocache().get(pk=live.pk).status, "live")
