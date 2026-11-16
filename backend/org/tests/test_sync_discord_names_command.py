from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from app.models import Organization
from discordbot.services.discord_members import DiscordMembersFetchError
from org.activity import guild_sync_lock
from org.discord_names import NameSyncResult

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_sync_discord_names_command",
    }
}
DUMMY = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

CMD = "org.management.commands.sync_discord_names"


def _member(discord_id: str, nick: str) -> dict:
    return {
        "user": {"id": discord_id, "username": f"u{discord_id}", "global_name": None},
        "nick": nick,
    }


@override_settings(CACHES=LOCMEM)
class SyncDiscordNamesCommandTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.org_a = Organization.objects.create(name="A", discord_server_id="111")
        self.org_b = Organization.objects.create(name="B", discord_server_id="111")
        self.org_c = Organization.objects.create(name="C", discord_server_id="222")
        Organization.objects.create(name="NoGuild", discord_server_id=None)
        Organization.objects.create(name="Blank", discord_server_id="")
        self.fetch = mock.patch(
            f"{CMD}.get_discord_members_data",
            side_effect=lambda guild_id, **_: [_member("42", f"nick-{guild_id}")],
        )
        self.apply = mock.patch(
            f"{CMD}.apply_guild_member_names",
            return_value=NameSyncResult(1, 2, 0),
        )
        self.fetch_mock = self.fetch.start()
        self.apply_mock = self.apply.start()
        self.addCleanup(mock.patch.stopall)

    def _run(self, *args: str) -> tuple[str, str]:
        out, err = StringIO(), StringIO()
        call_command("sync_discord_names", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    @override_settings(CACHEOPS_ENABLED=False)
    def test_refuses_when_cacheops_disabled(self) -> None:
        with self.assertRaisesMessage(CommandError, "docker exec"):
            self._run("--all")
        self.fetch_mock.assert_not_called()

    @override_settings(CACHES=DUMMY)
    def test_refuses_with_dummy_cache(self) -> None:
        with self.assertRaises(CommandError):
            self._run("--all")
        self.fetch_mock.assert_not_called()

    def test_runs_without_cacheops_override(self) -> None:
        self._run("--all")
        self.assertEqual(self.apply_mock.call_count, 2)

    def test_requires_org_or_all(self) -> None:
        with self.assertRaises(CommandError):
            self._run()

    def test_all_applies_once_per_guild(self) -> None:
        out, _ = self._run("--all")
        self.assertEqual(
            sorted(c.args[0] for c in self.fetch_mock.call_args_list), ["111", "222"]
        )
        for c in self.fetch_mock.call_args_list:
            self.assertTrue(c.kwargs["force"])
        calls = {c.args[0]: c for c in self.apply_mock.call_args_list}
        self.assertEqual(set(calls), {"111", "222"})
        self.assertEqual(
            sorted(calls["111"].args[1]), sorted([self.org_a.pk, self.org_b.pk])
        )
        self.assertEqual(calls["222"].args[1], [self.org_c.pk])
        for c in calls.values():
            self.assertIs(c.kwargs["complete"], True)
            self.assertIsInstance(c.kwargs["fetched_at"], float)
        self.assertEqual(calls["111"].args[2][0].nick, "nick-111")
        self.assertIn("users_updated=1", out)

    def test_org_syncs_every_org_on_its_guild(self) -> None:
        self._run("--org", str(self.org_a.pk))
        self.fetch_mock.assert_called_once()
        self.assertEqual(self.fetch_mock.call_args.args[0], "111")
        self.assertEqual(
            sorted(self.apply_mock.call_args.args[1]),
            sorted([self.org_a.pk, self.org_b.pk]),
        )

    def test_org_without_guild_errors(self) -> None:
        org = Organization.objects.get(name="Blank")
        with self.assertRaises(CommandError):
            self._run("--org", str(org.pk))

    def test_unknown_org_errors(self) -> None:
        with self.assertRaises(CommandError):
            self._run("--org", "999999")

    def test_locked_guild_skipped(self) -> None:
        self.assertTrue(guild_sync_lock("111"))
        _, err = self._run("--all")
        self.assertIn("111", err)
        self.assertEqual([c.args[0] for c in self.apply_mock.call_args_list], ["222"])
        self.assertFalse(guild_sync_lock("111"))

    def test_lock_released_after_run(self) -> None:
        self._run("--all")
        self.assertTrue(guild_sync_lock("111"))
        self.assertTrue(guild_sync_lock("222"))

    def test_fetch_failure_continues_releases_lock_and_exits_nonzero(self) -> None:
        def fetch(guild_id: str, **_: object) -> list[dict]:
            if guild_id == "111":
                raise DiscordMembersFetchError("403")
            return [_member("42", "n")]

        self.fetch_mock.side_effect = fetch
        with self.assertRaises(CommandError):
            self._run("--all")
        self.assertEqual([c.args[0] for c in self.apply_mock.call_args_list], ["222"])
        self.assertTrue(guild_sync_lock("111"))
