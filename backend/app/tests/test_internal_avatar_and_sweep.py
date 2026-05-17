"""Tests for the new batched-avatar and lease-sweep internal endpoints
added so celery workers no longer touch the ORM directly.

Routes under test:
- GET  /api/internal/users/discord-linked/
- GET  /api/internal/orgs/discord-guild-ids/
- POST /api/internal/users/avatars/bulk-update/
- POST /api/internal/discord/sweep-stale-leases/
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Organization

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class ListDiscordLinkedUsersTest(TestCase):
    """list_discord_linked_users returns Discord-linked users only."""

    def test_returns_only_users_with_discord_id(self):
        CustomUser.objects.create(
            username="linked", discordId="111", avatar="hash_a"
        )
        CustomUser.objects.create(
            username="no_discord", discordId=None, avatar="hash_b"
        )
        # Empty-string discord_id is excluded (treated as unset by the task)
        CustomUser.objects.create(
            username="blank_discord", discordId="", avatar="hash_c"
        )

        c = APIClient()
        resp = c.get("/api/internal/users/discord-linked/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        usernames = sorted(u["username"] for u in data)
        self.assertEqual(usernames, ["linked"])

    def test_returns_expected_fields(self):
        CustomUser.objects.create(
            username="alice", discordId="42", avatar="hash_x"
        )
        c = APIClient()
        resp = c.get("/api/internal/users/discord-linked/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(set(row.keys()), {"pk", "discord_id", "avatar", "username"})
        self.assertEqual(row["discord_id"], "42")
        self.assertEqual(row["avatar"], "hash_x")

    def test_requires_token(self):
        c = APIClient()
        resp = c.get("/api/internal/users/discord-linked/")
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class ListDiscordGuildIdsTest(TestCase):
    def test_returns_distinct_non_empty_ids(self):
        Organization.objects.create(name="A", discord_server_id="guild_1")
        Organization.objects.create(name="B", discord_server_id="guild_2")
        # Duplicate guild_id — must dedupe.
        Organization.objects.create(name="C", discord_server_id="guild_1")
        # No guild → excluded.
        Organization.objects.create(name="D", discord_server_id=None)
        Organization.objects.create(name="E", discord_server_id="")

        c = APIClient()
        resp = c.get("/api/internal/orgs/discord-guild-ids/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        guild_ids = sorted(resp.json()["guild_ids"])
        self.assertEqual(guild_ids, ["guild_1", "guild_2"])

    def test_empty_when_no_orgs(self):
        c = APIClient()
        resp = c.get("/api/internal/orgs/discord-guild-ids/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"guild_ids": []})

    def test_requires_token(self):
        c = APIClient()
        resp = c.get("/api/internal/orgs/discord-guild-ids/")
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class BulkUpdateUserAvatarsTest(TestCase):
    def test_updates_avatars_by_pk(self):
        u1 = CustomUser.objects.create(
            username="u1", discordId="1", avatar="old"
        )
        u2 = CustomUser.objects.create(
            username="u2", discordId="2", avatar="old"
        )

        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {
                "updates": [
                    {"pk": u1.pk, "avatar": "new_1"},
                    {"pk": u2.pk, "avatar": None},
                ]
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated"], 2)

        u1.refresh_from_db()
        u2.refresh_from_db()
        self.assertEqual(u1.avatar, "new_1")
        self.assertIsNone(u2.avatar)

    def test_empty_updates_is_noop(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": []},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated"], 0)

    def test_rejects_non_list_payload(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": "not a list"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_missing_pk_in_item(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": [{"avatar": "no_pk_here"}]},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_requires_token(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SweepStaleDiscordLeasesTest(TestCase):
    _next_id = 1000  # avoid colliding with other tests; bumped per row to
    # dodge the partial UniqueConstraint on (source, source_id) WHERE
    # success IS NOT FALSE.

    def _make_log(self, **kwargs):
        from discordbot.models import DiscordMessageLog

        cls = type(self)
        cls._next_id += 1
        defaults = {
            "channel_id": "123",
            "source": "event_announcement",
            "source_id": cls._next_id,
            "embed_data": {"title": "x"},
            "claimed_at": timezone.now(),
        }
        defaults.update(kwargs)
        return DiscordMessageLog.objects.create(**defaults)

    def test_sweeps_stale_pending_and_aged_failures(self):
        from discordbot.models import DiscordMessageLog

        now = timezone.now()
        # Stale pending (claimed >5 min ago, success NULL) → deleted
        self._make_log(claimed_at=now - timedelta(minutes=10), success=None)
        # Recent pending (only 1 min old) → kept
        self._make_log(claimed_at=now - timedelta(minutes=1), success=None)
        # Aged failure (>1 hour, success=False) → deleted
        self._make_log(claimed_at=now - timedelta(hours=2), success=False)
        # Recent failure (only 5 min old) → kept
        self._make_log(claimed_at=now - timedelta(minutes=5), success=False)
        # Successful log → never touched
        self._make_log(claimed_at=now - timedelta(hours=3), success=True)

        self.assertEqual(DiscordMessageLog.objects.count(), 5)

        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["pending_swept"], 1)
        self.assertEqual(body["failed_swept"], 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(DiscordMessageLog.objects.count(), 3)

    def test_custom_thresholds(self):
        from discordbot.models import DiscordMessageLog

        now = timezone.now()
        # Only 2 min old — below default 5-min threshold, but caller can lower it.
        self._make_log(claimed_at=now - timedelta(minutes=2), success=None)

        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": 1, "failed_threshold_hours": 24},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["pending_swept"], 1)
        self.assertEqual(DiscordMessageLog.objects.count(), 0)

    def test_rejects_non_integer_thresholds(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": "abc"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_requires_token(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/sweep-stale-leases/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
