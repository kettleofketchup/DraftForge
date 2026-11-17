import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

ARCHIVE_SQL = """
SELECT bp.user_id, u.username, u.steamid, u."discordId", bp.nickname
FROM user_baseuserprofile bp
JOIN app_customuser u ON u.id = bp.user_id
WHERE TRIM(COALESCE(bp.nickname, '')) <> ''
ORDER BY bp.user_id
"""
ARCHIVE_KEYS = ("user_id", "username", "steamid", "discordId", "nickname")


class Command(BaseCommand):
    help = (
        "Export every non-blank site nickname (user_baseuserprofile.nickname) "
        "to JSON before the column is dropped. Read-only."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--out", required=True, help="JSON file to create")

    def handle(self, *args: Any, **options: Any) -> None:
        out = Path(options["out"])
        if out.exists():
            raise CommandError(f"{out} already exists; refusing to overwrite")

        with connection.cursor() as cursor:
            cursor.execute(ARCHIVE_SQL)
            rows = [dict(zip(ARCHIVE_KEYS, row)) for row in cursor.fetchall()]

        with out.open("x", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
        self.stdout.write(f"Archived {len(rows)} site nicknames to {out}")
