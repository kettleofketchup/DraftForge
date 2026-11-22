"""Management command to run the Discord bot."""

from django.core.management.base import BaseCommand

from discordbot.bot import run_bot


class Command(BaseCommand):
    help = "Starts the Discord bot"

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(self.style.SUCCESS("Starting Discord bot..."))
        run_bot()
