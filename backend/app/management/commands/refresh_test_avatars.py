"""Rewrite tests/data/discord_avatars.py from the Discord API."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tests.populate.avatars import AVATARS_FILE, refresh_committed_avatars


class Command(BaseCommand):
    help = (
        "Fetch the real test users' Discord avatar hashes and commit them to test data"
    )

    def handle(self, *args: Any, **options: Any) -> None:
        token: str | None = settings.DISCORD_BOT_TOKEN
        if not token:
            raise CommandError("DISCORD_BOT_TOKEN is not set (backend/.env)")
        avatars, missing, failed = refresh_committed_avatars(token)
        self.stdout.write(f"Wrote {len(avatars)} avatars to {AVATARS_FILE}")
        if missing:
            self.stdout.write(f"No custom avatar: {', '.join(missing)}")
        if failed:
            raise CommandError(f"Fetch failed (kept old hash): {', '.join(failed)}")
