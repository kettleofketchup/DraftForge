"""Tests for `app.tasks.avatar_refresh.refresh_avatars_batched`.

The batched task delegates the heavy work — pagination + per-guild
caching — to `discordbot.services.users.get_discord_members_data`,
which is the project's canonical helper for fetching guild members.
We mock that helper here; pagination behavior is covered by the
helper's own tests in `discordbot/tests/test_discord_search.py`.

What this file owns:

  - test environment short-circuit (no Discord calls in TEST=true+DEBUG=true)
  - skip when no Discord-linked users exist
  - skip when no orgs with discord_server_id exist
  - successful match-and-update when guild members include our users
  - leaves user unchanged when avatar hash didn't change
  - per-guild fetch failure is logged and other guilds still process
  - multi-guild aggregation builds the right discord_id → avatar map
"""

from unittest.mock import patch

from django.test import TestCase

from app.models import CustomUser, Organization, PositionsModel
from app.tasks import avatar_refresh as ar


class AvatarRefreshBatchedTest(TestCase):
    """Coverage for the batched task in `app/tasks/avatar_refresh.py`."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="AR Org", discord_server_id="999000111"
        )

    def _make_user(self, *, username, discord_id=None, avatar=None):
        u = CustomUser.objects.create(
            username=username, positions=PositionsModel.objects.create()
        )
        if discord_id is not None:
            u.discordId = discord_id
        u.avatar = avatar
        u.save()
        return u

    # ---- early-exit branches -----------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=True)
    def test_test_environment_skips_work(self, _envcheck):
        """In test env (TEST=true + DEBUG=true) the task no-ops with skipped=True.

        Critical for the Playwright suite: prior to this gate, the prod task
        would block Daphne making real outbound Discord calls (all 401-ing).
        """
        result = ar.refresh_avatars_batched()
        self.assertEqual(result, {"checked": 0, "updated": 0, "skipped": True})

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_no_discordful_users_skips(self, mock_fetch, _envcheck):
        """Users without a discordId are skipped before any Discord call."""
        self._make_user(username="no_discord", discord_id=None)

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["updated"], 0)
        mock_fetch.assert_not_called()

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_no_orgs_with_guild_skips(self, mock_fetch, _envcheck):
        """Orgs without a discord_server_id contribute no guilds → no work."""
        self.org.discord_server_id = ""
        self.org.save()
        self._make_user(username="u1", discord_id="100", avatar="old_hash")

        result = ar.refresh_avatars_batched()

        self.assertEqual(result, {"checked": 1, "updated": 0})
        mock_fetch.assert_not_called()

    # ---- happy path ------------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_match_and_update_avatar(self, mock_fetch, _envcheck):
        """User's avatar hash differs from guild-members response → bulk update."""
        u = self._make_user(username="u1", discord_id="100", avatar="old_hash")
        mock_fetch.return_value = [
            {"user": {"id": "100", "avatar": "new_hash"}},
            {"user": {"id": "999", "avatar": "irrelevant"}},
        ]

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "new_hash")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["guilds"], 1)
        # Helper is called once per guild (the helper itself handles cache).
        mock_fetch.assert_called_once_with(guild_id="999000111")

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_unchanged_hash_skips_update(self, mock_fetch, _envcheck):
        """If guild-members reports the same avatar hash, no DB write happens."""
        u = self._make_user(username="u1", discord_id="100", avatar="same_hash")
        mock_fetch.return_value = [{"user": {"id": "100", "avatar": "same_hash"}}]

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "same_hash")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_user_not_in_any_guild_response_unchanged(self, mock_fetch, _envcheck):
        """If our user isn't in any returned guild member list, leave them alone.

        Covers the 'discord-linked user belongs to a guild we don't track'
        and 'guild fetch returned a partial list' edge cases — neither
        should clear or reset the local avatar.
        """
        u = self._make_user(username="orphan", discord_id="42", avatar="keep_me")
        mock_fetch.return_value = [{"user": {"id": "100", "avatar": "other_user"}}]

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "keep_me")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)

    # ---- error handling --------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_helper_exception_per_guild_does_not_abort(self, mock_fetch, _envcheck):
        """One guild raising must not abort the whole task — other guilds
        still get processed and the local user's avatar is updated from
        whichever guild succeeds.
        """
        # Two orgs / two guilds — helper raises for the first, returns
        # data for the second.
        Organization.objects.create(
            name="Second Org", discord_server_id="222111000"
        )
        u = self._make_user(username="u1", discord_id="100", avatar="old")
        mock_fetch.side_effect = [
            Exception("simulated Discord 503"),
            [{"user": {"id": "100", "avatar": "new"}}],
        ]

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "new")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["guilds"], 2)
        self.assertEqual(mock_fetch.call_count, 2)

    # ---- multi-guild aggregation -----------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch("discordbot.services.users.get_discord_members_data")
    def test_multi_guild_aggregates_avatar_map(self, mock_fetch, _envcheck):
        """Users found via guild B still get updated when guild A doesn't have them."""
        Organization.objects.create(
            name="Org B", discord_server_id="222111000"
        )
        u_a = self._make_user(username="u_a", discord_id="100", avatar="old_a")
        u_b = self._make_user(username="u_b", discord_id="200", avatar="old_b")
        # Each guild only contains one of our local users.
        mock_fetch.side_effect = [
            [{"user": {"id": "100", "avatar": "new_a"}}],
            [{"user": {"id": "200", "avatar": "new_b"}}],
        ]

        result = ar.refresh_avatars_batched()

        u_a.refresh_from_db()
        u_b.refresh_from_db()
        self.assertEqual(u_a.avatar, "new_a")
        self.assertEqual(u_b.avatar, "new_b")
        self.assertEqual(result["updated"], 2)
        self.assertEqual(result["guilds"], 2)
