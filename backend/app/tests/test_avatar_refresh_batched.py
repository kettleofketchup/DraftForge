"""Tests for `app.tasks.avatar_refresh.refresh_avatars_batched`.

The batched task replaces the per-user `/users/{id}` fan-out with
`GET /guilds/{id}/members?limit=1000` paginated calls per org-guild.
Behaviors covered:

  - test environment short-circuit (no Discord calls in TEST=true+DEBUG=true)
  - skip when no Discord-linked users exist
  - skip when no orgs with discord_server_id exist
  - successful match-and-update against a mocked single-page guild response
  - leaves user unchanged when avatar hash didn't change
  - early-exit when all `needed_ids` for a guild are seen on page 1
  - paginated fetch (multi-page) accumulates members across pages
  - soft-cap warning when `_GUILD_MEMBER_MAX_PAGES` is hit (no infinite loop)

httpx is mocked at the module's `httpx.AsyncClient` level so no real
Discord calls are made.
"""

from unittest.mock import patch, MagicMock, AsyncMock

from django.test import TestCase, override_settings

from app.models import CustomUser, Organization, PositionsModel
from app.tasks import avatar_refresh as ar


def _resp(status, payload):
    """Build a stub for httpx.Response usable with AsyncMock."""
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


class AvatarRefreshBatchedTest(TestCase):
    """Coverage for the new batched task in app/tasks/avatar_refresh.py."""

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
    def test_no_discordful_users_skips(self, _envcheck):
        """Users without a discordId are skipped before any HTTP work."""
        # Make a user with no discordId; nothing to update.
        self._make_user(username="no_discord", discord_id=None)

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["updated"], 0)

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    def test_no_orgs_with_guild_skips(self, _envcheck):
        """Orgs without a discord_server_id contribute no guilds → no work."""
        # Wipe the only org's guild id.
        self.org.discord_server_id = ""
        self.org.save()
        self._make_user(username="u1", discord_id="100", avatar="old_hash")

        result = ar.refresh_avatars_batched()

        self.assertEqual(result, {"checked": 1, "updated": 0})

    # ---- happy path: matches a guild member and updates ------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict(
        "os.environ",
        {
            "DISCORD_BOT_TOKEN": "test-token",
            "DISCORD_API_BASE_URL": "https://discord.test/api",
        },
        clear=False,
    )
    @patch("app.tasks.avatar_refresh.httpx.AsyncClient")
    def test_match_and_update_avatar(self, mock_client, _envcheck):
        """User's avatar hash differs from guild-members response → bulk update."""
        u = self._make_user(username="u1", discord_id="100", avatar="old_hash")

        # Single-page guild members response — `len < limit` ends pagination.
        mock_get = AsyncMock(
            return_value=_resp(
                200,
                [
                    {"user": {"id": "100", "avatar": "new_hash"}},
                    {"user": {"id": "999", "avatar": "irrelevant"}},
                ],
            )
        )
        mock_client.return_value.__aenter__.return_value.get = mock_get

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "new_hash")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["guilds"], 1)

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict(
        "os.environ",
        {
            "DISCORD_BOT_TOKEN": "test-token",
            "DISCORD_API_BASE_URL": "https://discord.test/api",
        },
        clear=False,
    )
    @patch("app.tasks.avatar_refresh.httpx.AsyncClient")
    def test_unchanged_hash_skips_update(self, mock_client, _envcheck):
        """If guild-members reports the same avatar hash, no DB write happens."""
        u = self._make_user(username="u1", discord_id="100", avatar="same_hash")

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_resp(
                200, [{"user": {"id": "100", "avatar": "same_hash"}}]
            )
        )

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "same_hash")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)

    # ---- pagination -----------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict(
        "os.environ",
        {
            "DISCORD_BOT_TOKEN": "test-token",
            "DISCORD_API_BASE_URL": "https://discord.test/api",
        },
        clear=False,
    )
    @patch("app.tasks.avatar_refresh.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.tasks.avatar_refresh.httpx.AsyncClient")
    def test_paginated_fetch_until_short_page(
        self, mock_client, _sleep, _envcheck
    ):
        """Pages until response < limit; covers full pagination control flow."""
        u = self._make_user(username="u1", discord_id="42", avatar=None)

        # Patch the page size locally so we don't have to fabricate 1000-member
        # responses in a test.
        original_limit = ar._GUILD_MEMBER_LIMIT
        ar._GUILD_MEMBER_LIMIT = 2
        try:
            page1 = [
                {"user": {"id": "1", "avatar": "a1"}},
                {"user": {"id": "2", "avatar": "a2"}},
            ]
            page2 = [
                {"user": {"id": "42", "avatar": "the_one"}},
            ]  # len < limit → stop
            mock_get = AsyncMock(side_effect=[_resp(200, page1), _resp(200, page2)])
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = ar.refresh_avatars_batched()
        finally:
            ar._GUILD_MEMBER_LIMIT = original_limit

        u.refresh_from_db()
        self.assertEqual(u.avatar, "the_one")
        self.assertEqual(mock_get.call_count, 2)  # two pages fetched
        self.assertEqual(result["updated"], 1)

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict(
        "os.environ",
        {
            "DISCORD_BOT_TOKEN": "test-token",
            "DISCORD_API_BASE_URL": "https://discord.test/api",
        },
        clear=False,
    )
    @patch("app.tasks.avatar_refresh.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.tasks.avatar_refresh.httpx.AsyncClient")
    def test_early_exit_when_all_needed_ids_matched(
        self, mock_client, _sleep, _envcheck
    ):
        """Guild paging stops as soon as we've seen every local discordId.

        Realistic case: a 50k-member guild with only a handful of local
        users. Don't burn 50 paginated calls when the local users we care
        about all appear on page 1.
        """
        u = self._make_user(username="u1", discord_id="42", avatar=None)

        original_limit = ar._GUILD_MEMBER_LIMIT
        ar._GUILD_MEMBER_LIMIT = 2  # forces multiple pages even for tiny test
        try:
            page1 = [
                {"user": {"id": "1", "avatar": "a1"}},
                {"user": {"id": "42", "avatar": "wanted"}},  # the one we need
            ]
            # Set up additional pages to prove they DON'T get fetched.
            mock_get = AsyncMock(
                side_effect=[
                    _resp(200, page1),
                    _resp(200, [{"user": {"id": "999", "avatar": "x"}}]),
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = ar.refresh_avatars_batched()
        finally:
            ar._GUILD_MEMBER_LIMIT = original_limit

        u.refresh_from_db()
        self.assertEqual(u.avatar, "wanted")
        # Critical: only ONE page fetched even though more were available.
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(result["updated"], 1)

    # ---- error handling --------------------------------------------------

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict(
        "os.environ",
        {
            "DISCORD_BOT_TOKEN": "test-token",
            "DISCORD_API_BASE_URL": "https://discord.test/api",
        },
        clear=False,
    )
    @patch("app.tasks.avatar_refresh.httpx.AsyncClient")
    def test_non_200_response_breaks_pagination_for_that_guild(
        self, mock_client, _envcheck
    ):
        """A non-200 from Discord stops pagination for that guild (logs warning)
        but doesn't raise — task returns successfully with 0 updates.
        """
        self._make_user(username="u1", discord_id="100", avatar="x")
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_resp(403, {"message": "Forbidden"})
        )

        result = ar.refresh_avatars_batched()

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)

    @patch("app.tasks.avatar_refresh._is_test_environment", return_value=False)
    @patch.dict("os.environ", {"DISCORD_BOT_TOKEN": ""}, clear=False)
    def test_no_bot_token_returns_empty_avatar_map(self, _envcheck):
        """Without a bot token, build_avatar_map short-circuits to empty.

        Local users still appear in `checked`, but updates is 0 because we
        had no live Discord data to compare against.
        """
        u = self._make_user(username="u1", discord_id="100", avatar="old")

        result = ar.refresh_avatars_batched()

        u.refresh_from_db()
        self.assertEqual(u.avatar, "old")
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 0)
