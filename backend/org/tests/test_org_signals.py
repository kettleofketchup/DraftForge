import weakref

from django.db.models.signals import ModelSignal, post_save, pre_save
from django.test import SimpleTestCase


class OrgSignalRegistrationTests(SimpleTestCase):
    def test_org_receivers_registered_once(self) -> None:
        cases: list[tuple[ModelSignal, str]] = [
            (pre_save, "org_track_discord_server_id"),
            (post_save, "org_reset_guild_nicknames"),
        ]
        for signal, uid in cases:
            with self.subTest(uid=uid):
                entries = [e for e in signal.receivers if e[0][0] == uid]
                self.assertEqual(len(entries), 1)
                receiver = entries[0][1]
                if isinstance(receiver, weakref.ReferenceType):
                    receiver = receiver()
                self.assertEqual(receiver.__module__, "org.signals")
