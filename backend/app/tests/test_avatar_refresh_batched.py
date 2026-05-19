"""Tests for `app.tasks.avatar_refresh.refresh_avatars_batched`.

The batched task no longer touches the ORM — all DB I/O goes through
`internal_client` HTTP calls. These tests patch the wrapper functions
and assert the task assembled the right update payload, picked the
right guilds, and exited cleanly on the early-out branches.

DB-side correctness of the wrapper endpoints is covered separately by
`test_internal_avatar_and_sweep.py`.
"""

from unittest.mock import patch

from django.test import TestCase

from app.tasks import avatar_refresh as ar


def _user_row(*, pk, discord_id, avatar=None, username=None):
    """Shape returned by /api/internal/users/discord-linked/."""
    return {
        "pk": pk,
        "discord_id": discord_id,
        "avatar": avatar,
        "username": username or f"u{pk}",
    }


class AvatarRefreshBatchedTest(TestCase):
    """Coverage for the batched task in `app/tasks/avatar_refresh.py`."""

    # ---- early-exit branches -----------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=True)
    def test_test_environment_skips_work(self, _envcheck):
        """In test env (TEST=true + DEBUG=true) the task no-ops with skipped=True."""
        result = ar.refresh_avatars_batched()
        self.assertEqual(result, {"checked": 0, "updated": 0, "skipped": True})

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("app.internal_client.list_discord_linked_users", return_value=[])
    @patch("app.internal_client.list_discord_guild_ids")
    @patch("app.internal_client.bulk_update_user_avatars")
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_no_discordful_users_skips(
        self, mock_fetch, mock_bulk, mock_guilds, mock_users, _envcheck
    ):
        """Empty user list skips guilds/discord/bulk entirely."""
        result = ar.refresh_avatars_batched()

        self.assertEqual(result, {"checked": 0, "updated": 0})
        mock_guilds.assert_not_called()
        mock_fetch.assert_not_called()
        mock_bulk.assert_not_called()

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[_user_row(pk=1, discord_id="100", avatar="old_hash")],
    )
    @patch("app.internal_client.list_discord_guild_ids", return_value=[])
    @patch("app.internal_client.bulk_update_user_avatars")
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_no_orgs_with_guild_skips(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """No guilds → still report user count but skip Discord and bulk-update."""
        result = ar.refresh_avatars_batched()

        self.assertEqual(result, {"checked": 1, "updated": 0})
        mock_fetch.assert_not_called()
        mock_bulk.assert_not_called()

    # ---- happy path ------------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[_user_row(pk=1, discord_id="100", avatar="old_hash")],
    )
    @patch(
        "app.internal_client.list_discord_guild_ids",
        return_value=["999000111"],
    )
    @patch("app.internal_client.bulk_update_user_avatars", return_value=1)
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_match_and_update_avatar(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """User's avatar hash differs from guild-members response → bulk update."""
        mock_fetch.return_value = [
            {"user": {"id": "100", "avatar": "new_hash"}},
            {"user": {"id": "999", "avatar": "irrelevant"}},
        ]

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["guilds"], 1)
        mock_fetch.assert_called_once_with(guild_id="999000111")
        mock_bulk.assert_called_once_with([{"pk": 1, "avatar": "new_hash"}])

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[_user_row(pk=1, discord_id="100", avatar="same_hash")],
    )
    @patch(
        "app.internal_client.list_discord_guild_ids",
        return_value=["999000111"],
    )
    @patch("app.internal_client.bulk_update_user_avatars")
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_unchanged_hash_skips_update(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """If guild-members reports the same hash, the bulk-update endpoint
        is never called (no payload to send)."""
        mock_fetch.return_value = [{"user": {"id": "100", "avatar": "same_hash"}}]

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)
        mock_bulk.assert_not_called()

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[_user_row(pk=1, discord_id="42", avatar="keep_me")],
    )
    @patch(
        "app.internal_client.list_discord_guild_ids",
        return_value=["999000111"],
    )
    @patch("app.internal_client.bulk_update_user_avatars")
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_user_not_in_any_guild_response_unchanged(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """User not in any returned member list → no update payload at all."""
        mock_fetch.return_value = [{"user": {"id": "100", "avatar": "other_user"}}]

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)
        mock_bulk.assert_not_called()

    # ---- error handling --------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[_user_row(pk=1, discord_id="100", avatar="old")],
    )
    @patch(
        "app.internal_client.list_discord_guild_ids",
        return_value=["999000111", "222111000"],
    )
    @patch("app.internal_client.bulk_update_user_avatars", return_value=1)
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_helper_exception_per_guild_does_not_abort(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """One guild raising must not abort the whole task."""
        mock_fetch.side_effect = [
            Exception("simulated Discord 503"),
            [{"user": {"id": "100", "avatar": "new"}}],
        ]

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["guilds"], 2)
        self.assertEqual(mock_fetch.call_count, 2)
        mock_bulk.assert_called_once_with([{"pk": 1, "avatar": "new"}])

    # ---- multi-guild aggregation -----------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch(
        "app.internal_client.list_discord_linked_users",
        return_value=[
            _user_row(pk=1, discord_id="100", avatar="old_a"),
            _user_row(pk=2, discord_id="200", avatar="old_b"),
        ],
    )
    @patch(
        "app.internal_client.list_discord_guild_ids",
        return_value=["999000111", "222111000"],
    )
    @patch("app.internal_client.bulk_update_user_avatars", return_value=2)
    @patch("discordbot.services.discord_members.get_discord_members_data")
    def test_multi_guild_aggregates_avatar_map(
        self, mock_fetch, mock_bulk, _mock_guilds, _mock_users, _envcheck
    ):
        """Users found via guild B still get updated when guild A doesn't have them."""
        mock_fetch.side_effect = [
            [{"user": {"id": "100", "avatar": "new_a"}}],
            [{"user": {"id": "200", "avatar": "new_b"}}],
        ]

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["updated"], 2)
        self.assertEqual(result["guilds"], 2)
        # Order matters in the call: pk=1 came first in the user list.
        mock_bulk.assert_called_once()
        sent_updates = mock_bulk.call_args.args[0]
        self.assertEqual(
            sorted(sent_updates, key=lambda r: r["pk"]),
            [
                {"pk": 1, "avatar": "new_a"},
                {"pk": 2, "avatar": "new_b"},
            ],
        )
