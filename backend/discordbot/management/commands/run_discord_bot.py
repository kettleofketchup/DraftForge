"""Management command to run the Discord bot."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Starts the Discord bot"

    def handle(self, *args, **options):
        from discordbot.bot import run_bot

        self.stdout.write(self.style.SUCCESS("Starting Discord bot..."))
        run_bot()
