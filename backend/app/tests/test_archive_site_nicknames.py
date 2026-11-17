import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase

from app.models import CustomUser


def _set_raw_nickname(user: CustomUser, value: str | None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE user_baseuserprofile SET nickname = %s WHERE user_id = %s",
            [value, user.pk],
        )


class ArchiveSiteNicknamesTest(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "site-nicknames.json"

        self.named = CustomUser.objects.create(
            username="archive_named", steamid=76561198000000001, discordId="9001"
        )
        _set_raw_nickname(self.named, "Shadow")
        self.steam_only = CustomUser.objects.create(steamid=76561198000000002)
        _set_raw_nickname(self.steam_only, " Ghost ")
        blank = CustomUser.objects.create(username="archive_blank")
        _set_raw_nickname(blank, "   ")
        empty = CustomUser.objects.create(username="archive_empty")
        _set_raw_nickname(empty, "")
        CustomUser.objects.create(username="archive_null")

    def test_writes_only_non_blank_nicknames(self) -> None:
        stdout = StringIO()
        call_command("archive_site_nicknames", "--out", str(self.out), stdout=stdout)

        rows = json.loads(self.out.read_text())
        by_user = {row["user_id"]: row for row in rows}
        self.assertEqual(set(by_user), {self.named.pk, self.steam_only.pk})
        self.assertEqual(
            by_user[self.named.pk],
            {
                "user_id": self.named.pk,
                "username": "archive_named",
                "steamid": 76561198000000001,
                "discordId": "9001",
                "nickname": "Shadow",
            },
        )
        self.assertIsNone(by_user[self.steam_only.pk]["username"])
        self.assertEqual(by_user[self.steam_only.pk]["nickname"], " Ghost ")
        self.assertIn("2", stdout.getvalue())

    def test_refuses_existing_out(self) -> None:
        self.out.write_text("keep")
        with self.assertRaises(CommandError):
            call_command("archive_site_nicknames", "--out", str(self.out))
        self.assertEqual(self.out.read_text(), "keep")
