"""Tests for the internal batched-avatar endpoints."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class ListDiscordLinkedUsersTest(TestCase):
    """list_discord_linked_users returns Discord-linked users only."""

    def test_returns_only_users_with_discord_id(self) -> None:
        CustomUser.objects.create(username="linked", discordId="111", avatar="hash_a")
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

    def test_returns_expected_fields(self) -> None:
        CustomUser.objects.create(username="alice", discordId="42", avatar="hash_x")
        c = APIClient()
        resp = c.get("/api/internal/users/discord-linked/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(set(row.keys()), {"pk", "discord_id", "avatar", "username"})
        self.assertEqual(row["discord_id"], "42")
        self.assertEqual(row["avatar"], "hash_x")

    def test_requires_token(self) -> None:
        c = APIClient()
        resp = c.get("/api/internal/users/discord-linked/")
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class ListDiscordGuildIdsTest(TestCase):
    def test_returns_distinct_non_empty_ids(self) -> None:
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

    def test_empty_when_no_orgs(self) -> None:
        c = APIClient()
        resp = c.get("/api/internal/orgs/discord-guild-ids/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"guild_ids": []})

    def test_requires_token(self) -> None:
        c = APIClient()
        resp = c.get("/api/internal/orgs/discord-guild-ids/")
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class BulkUpdateUserAvatarsTest(TestCase):
    def test_updates_avatars_by_pk(self) -> None:
        u1 = CustomUser.objects.create(username="u1", discordId="1", avatar="old")
        u2 = CustomUser.objects.create(username="u2", discordId="2", avatar="old")

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

    def test_empty_updates_is_noop(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": []},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated"], 0)

    def test_rejects_non_list_payload(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": "not a list"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_missing_pk_in_item(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": [{"avatar": "no_pk_here"}]},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_non_integer_pk(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": [{"pk": "not_an_int", "avatar": "x"}]},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("pk", resp.json()["error"])

    def test_rejects_bool_pk(self) -> None:
        # bool is a subclass of int in Python — explicitly rejected so
        # {"pk": True} doesn't silently update pk=1.
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": [{"pk": True, "avatar": "x"}]},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_non_dict_item(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": ["this is not a dict"]},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_no_partial_writes_on_validation_failure(self) -> None:
        """Validation runs before any bulk_update; a bad item late in the
        list must not leave earlier items written."""
        u = CustomUser.objects.create(
            username="alice", discordId="42", avatar="original"
        )
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {
                "updates": [
                    {"pk": u.pk, "avatar": "would_be_new"},
                    {"pk": "bogus", "avatar": "x"},  # bails here
                ]
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)
        u.refresh_from_db()
        self.assertEqual(u.avatar, "original")

    def test_requires_token(self) -> None:
        c = APIClient()
        resp = c.post(
            "/api/internal/users/avatars/bulk-update/",
            {"updates": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
