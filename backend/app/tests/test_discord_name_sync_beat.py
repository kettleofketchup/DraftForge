"""sync-active-org-discord-names must be in both beat schedules.

Parsed rather than imported: importing celery_light sets up Django with the
worker settings.
"""

from django.test import SimpleTestCase

from lobby.tests.test_beat_schedule import beat_schedule


class DiscordNameSyncBeatTests(SimpleTestCase):
    def test_entry_in_both_schedules(self) -> None:
        for filename in ("celery.py", "celery_light.py"):
            with self.subTest(filename=filename):
                entry = beat_schedule(filename)["sync-active-org-discord-names"]
                self.assertEqual(
                    entry["task"],
                    "app.tasks.discord_name_sync.sync_active_org_discord_names",
                )
                self.assertEqual(entry["schedule"], 1800.0)
