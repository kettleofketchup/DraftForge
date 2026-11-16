from unittest.mock import MagicMock, call, patch

from celery.exceptions import SoftTimeLimitExceeded
from django.test import SimpleTestCase

from app.tasks import discord_name_sync
from app.tasks.discord_name_sync import (
    sync_active_org_discord_names,
    sync_org_discord_names,
)
from discordbot.services.discord_members import DiscordMembersFetchError

MODULE = "app.tasks.discord_name_sync"


def _member(discord_id: str, nick: str | None = None) -> dict:
    return {
        "user": {
            "id": discord_id,
            "username": f"u{discord_id}",
            "global_name": f"G{discord_id}",
        },
        "nick": nick,
    }


class DiscordNameSyncTaskTests(SimpleTestCase):
    def setUp(self) -> None:
        patches = {
            "targets": patch(f"{MODULE}.list_discord_name_sync_targets"),
            "fetch": patch(f"{MODULE}.get_discord_members_data"),
            "post": patch(f"{MODULE}.bulk_update_member_names"),
            "test_env": patch(f"{MODULE}._is_test_environment", return_value=False),
        }
        self.mocks: dict[str, MagicMock] = {}
        for name, p in patches.items():
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)
        self.mocks["targets"].return_value = [
            {"org_id": 1, "guild_id": "111"},
            {"org_id": 2, "guild_id": "111"},
            {"org_id": 3, "guild_id": "222"},
        ]
        self.mocks["fetch"].side_effect = lambda guild_id, **kw: [
            _member(f"{guild_id}1", "Nick")
        ]
        self.mocks["post"].return_value = {
            "users_updated": 0,
            "org_users_updated": 0,
            "org_users_cleared": 0,
        }

    def test_fetches_each_guild_once_and_posts_grouped_org_ids(self) -> None:
        sync_active_org_discord_names()

        self.mocks["targets"].assert_called_once_with(scope="active", lock=True)
        self.assertEqual(
            self.mocks["fetch"].call_args_list,
            [
                call("111", force=True, write_cache=False),
                call("222", force=True, write_cache=False),
            ],
        )
        self.assertEqual(self.mocks["post"].call_count, 2)
        first = self.mocks["post"].call_args_list[0]
        self.assertEqual(first.args[0], "111")
        self.assertEqual(first.args[1], [1, 2])
        self.assertEqual(
            first.args[2],
            [
                {
                    "discord_id": "1111",
                    "username": "u1111",
                    "nick": "Nick",
                    "global_name": "G1111",
                }
            ],
        )
        self.assertIs(first.kwargs["complete"], True)
        self.assertIsInstance(first.kwargs["fetched_at"], float)
        self.assertEqual(self.mocks["post"].call_args_list[1].args[:2], ("222", [3]))

    def test_failed_guild_fetch_skips_that_guild_only(self) -> None:
        def fetch(guild_id: str, **kwargs: object) -> list[dict]:
            if guild_id == "111":
                raise DiscordMembersFetchError("403 Missing Access")
            return [_member("2221")]

        self.mocks["fetch"].side_effect = fetch

        sync_active_org_discord_names()

        self.assertEqual(self.mocks["post"].call_count, 1)
        self.assertEqual(self.mocks["post"].call_args.args[:2], ("222", [3]))

    def test_empty_member_list_is_not_posted(self) -> None:
        self.mocks["fetch"].side_effect = lambda guild_id, **kw: []

        sync_active_org_discord_names()

        self.mocks["post"].assert_not_called()

    def test_test_environment_makes_no_client_calls(self) -> None:
        self.mocks["test_env"].return_value = True

        sync_active_org_discord_names()
        sync_org_discord_names(5)

        self.mocks["targets"].assert_not_called()
        self.mocks["fetch"].assert_not_called()
        self.mocks["post"].assert_not_called()

    def test_single_org_sync_requests_all_scope_for_that_org(self) -> None:
        self.mocks["targets"].return_value = [{"org_id": 5, "guild_id": "555"}]

        sync_org_discord_names(5)

        self.mocks["targets"].assert_called_once_with(scope="all", org_id=5, lock=True)
        self.assertEqual(self.mocks["post"].call_args.args[:2], ("555", [5]))

    def test_soft_time_limit_ends_the_run(self) -> None:
        self.mocks["fetch"].side_effect = SoftTimeLimitExceeded()

        with self.assertRaises(SoftTimeLimitExceeded):
            discord_name_sync._sync_targets(self.mocks["targets"].return_value)

        self.assertEqual(self.mocks["fetch"].call_count, 1)
        self.mocks["post"].assert_not_called()

    def test_task_time_limits(self) -> None:
        for task in (sync_active_org_discord_names, sync_org_discord_names):
            with self.subTest(task=task.name):
                self.assertEqual(task.soft_time_limit, 300)
                self.assertEqual(task.time_limit, 360)
                self.assertTrue(task.ignore_result)
