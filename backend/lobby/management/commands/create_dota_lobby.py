"""Request a dota_lobby lobby for one game, as an organizer would."""

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from app.models import Game
from lobby import services


class Command(BaseCommand):
    help = (
        "Request a dota_lobby lobby for a game (manual trigger). The create "
        "itself runs in Celery."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("game_id", type=int)
        parser.add_argument(
            "--allow-missing",
            action="store_true",
            help="Leave out players without a Steam account ID",
        )
        parser.add_argument(
            "--replay",
            action="store_true",
            help="Host the match again although a lobby already played it",
        )

    def handle(self, *args: object, **options: object) -> None:
        try:
            game = Game.objects.select_related(
                "tournament", "radiant_team", "dire_team"
            ).get(pk=options["game_id"])
        except Game.DoesNotExist:
            raise CommandError(f"No game {options['game_id']}") from None
        with transaction.atomic():
            eligibility = services.queue_create(
                game,
                allow_missing=bool(options["allow_missing"]),
                replay=bool(options["replay"]),
            )
        if not eligibility.ok:
            raise CommandError(f"{eligibility.code} {eligibility.details or ''}")
        self.stdout.write(f"Lobby requested for game {game.pk}")
