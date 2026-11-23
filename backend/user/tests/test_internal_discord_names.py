from datetime import timedelta
from typing import Any
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import app.internal_client as internal_client
from app.models import CustomUser
from league.models import League
from org.activity import guild_sync_lock
from org.models import Organization, OrgUser
from tournament.models import Tournament
from user.internal import discord_names as internal_discord_names

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}
LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_internal_discord_names",
    }
}
TARGETS_URL = "/api/internal/orgs/discord-name-sync-targets/"
BULK_URL = "/api/internal/discord/member-names/bulk-update/"


def _make_active(org: Organization) -> None:
    league = League.objects.create(name=f"{org.name} league", organization=org)
    Tournament.objects.create(
        name=f"{org.name} cup",
        date_played=timezone.now() + timedelta(days=1),
        league=league,
    )


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN, CACHES=LOCMEM)
class DiscordNameSyncTargetsTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.a = Organization.objects.create(name="A", discord_server_id="111")
        self.b = Organization.objects.create(name="B", discord_server_id="111")
        self.c = Organization.objects.create(name="C", discord_server_id="222")
        self.none = Organization.objects.create(name="N", discord_server_id=None)
        self.blank = Organization.objects.create(name="E", discord_server_id="")

    def _get(self, **params: Any) -> list[dict[str, Any]]:
        resp = self.client.get(TARGETS_URL, params, **HEADERS)
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_url_name(self) -> None:
        self.assertEqual(reverse("internal_discord_name_sync_targets"), TARGETS_URL)

    def test_requires_internal_token(self) -> None:
        resp = self.client.get(TARGETS_URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_active_scope_returns_orgs_with_current_tournaments(self) -> None:
        _make_active(self.a)
        _make_active(self.c)
        _make_active(self.none)
        _make_active(self.blank)
        rows = self._get(scope="active")
        self.assertEqual(
            sorted((r["org_id"], r["guild_id"]) for r in rows),
            sorted([(self.a.pk, "111"), (self.c.pk, "222")]),
        )

    def test_default_scope_is_active(self) -> None:
        _make_active(self.c)
        self.assertEqual(self._get(), [{"org_id": self.c.pk, "guild_id": "222"}])

    def test_empty_guild_orgs_never_returned(self) -> None:
        rows = self._get(scope="all")
        org_ids = {r["org_id"] for r in rows}
        self.assertNotIn(self.none.pk, org_ids)
        self.assertNotIn(self.blank.pk, org_ids)
        self.assertTrue(all(r["guild_id"] for r in rows))

    def test_all_scope_with_org_returns_guild_siblings(self) -> None:
        rows = self._get(scope="all", org_id=self.a.pk)
        self.assertEqual(
            sorted(r["org_id"] for r in rows), sorted([self.a.pk, self.b.pk])
        )
        self.assertTrue(all(r["guild_id"] == "111" for r in rows))

    def test_all_scope_with_guildless_org_returns_empty(self) -> None:
        self.assertEqual(self._get(scope="all", org_id=self.blank.pk), [])
        self.assertEqual(self._get(scope="all", org_id=999_999), [])

    def test_lock_omits_guild_on_second_call(self) -> None:
        first = self._get(scope="all", org_id=self.a.pk, lock=1)
        self.assertEqual(len(first), 2)
        self.assertEqual(self._get(scope="all", org_id=self.a.pk, lock=1), [])
        self.assertFalse(guild_sync_lock("111"))

    def test_lock_skips_only_locked_guilds(self) -> None:
        _make_active(self.a)
        _make_active(self.c)
        self.assertTrue(guild_sync_lock("111"))
        rows = self._get(scope="active", lock=1)
        self.assertEqual(rows, [{"org_id": self.c.pk, "guild_id": "222"}])

    def test_without_lock_does_not_take_lock(self) -> None:
        self._get(scope="all", org_id=self.a.pk)
        self.assertTrue(guild_sync_lock("111"))

    def test_invalid_params_rejected(self) -> None:
        for params in ({"scope": "bogus"}, {"scope": "all", "org_id": "x"}):
            resp = self.client.get(TARGETS_URL, params, **HEADERS)
            self.assertEqual(resp.status_code, 400, params)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN, CACHES=LOCMEM)
class BulkUpdateMemberNamesTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.org = Organization.objects.create(name="A", discord_server_id="111")
        self.user = CustomUser.objects.create(
            username="dragonclaw", discordId="42", discordUsername="dc_old"
        )
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)

    def _body(self, **overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "guild_id": "111",
            "org_ids": [self.org.pk],
            "complete": True,
            "fetched_at": 1000.5,
            "members": [
                {
                    "discord_id": "42",
                    "username": "dc_new",
                    "nick": "DragonClaw",
                    "global_name": "GwaihirTheWindlord",
                }
            ],
        }
        body.update(overrides)
        return body

    def _post(self, body: dict[str, Any]) -> Any:
        return self.client.post(BULK_URL, body, format="json", **HEADERS)

    def _assert_unchanged(self) -> None:
        self.user.refresh_from_db()
        self.org_user.refresh_from_db()
        self.assertIsNone(self.user.discordNickname)
        self.assertEqual(self.user.discordUsername, "dc_old")
        self.assertIsNone(self.org_user.guild_nickname)

    def test_url_name(self) -> None:
        self.assertEqual(reverse("internal_discord_member_names_bulk_update"), BULK_URL)

    def test_requires_internal_token(self) -> None:
        resp = self.client.post(BULK_URL, self._body(), format="json")
        self.assertIn(resp.status_code, (401, 403))
        self._assert_unchanged()

    def test_valid_body_applies_and_releases_lock(self) -> None:
        self.assertTrue(guild_sync_lock("111"))
        resp = self._post(self._body())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(),
            {"users_updated": 1, "org_users_updated": 1, "org_users_cleared": 0},
        )
        self.user.refresh_from_db()
        self.org_user.refresh_from_db()
        self.assertEqual(self.user.discordNickname, "GwaihirTheWindlord")
        self.assertEqual(self.user.discordUsername, "dc_new")
        self.assertEqual(self.org_user.guild_nickname, "DragonClaw")
        self.assertTrue(guild_sync_lock("111"))

    def test_single_member_partial_payload_valid(self) -> None:
        resp = self._post(self._body(complete=False, fetched_at=None))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.org_user.refresh_from_db()
        self.assertEqual(self.org_user.guild_nickname, "DragonClaw")

    def test_invalid_bodies_rejected_without_write(self) -> None:
        member = self._body()["members"][0]
        cases: list[dict[str, Any]] = [
            self._body(members="nope"),
            self._body(members=[{**member, "discord_id": 42}]),
            self._body(members=[{**member, "nick": 5}]),
            self._body(members=["x"]),
            self._body(guild_id=""),
            self._body(guild_id=111),
            self._body(org_ids=[True]),
            self._body(org_ids="1"),
            self._body(complete="yes"),
            self._body(fetched_at="now"),
        ]
        missing_complete = self._body()
        del missing_complete["complete"]
        cases.append(missing_complete)
        for body in cases:
            resp = self._post(body)
            self.assertEqual(resp.status_code, 400, body)
        self._assert_unchanged()

    def test_member_cap_enforced(self) -> None:
        member = self._body()["members"][0]
        with mock.patch("user.internal.discord_names.MAX_MEMBERS", 2):
            resp = self._post(self._body(members=[member] * 3))
        self.assertEqual(resp.status_code, 400)
        self._assert_unchanged()

    def test_default_cap_is_50k(self) -> None:
        self.assertEqual(internal_discord_names.MAX_MEMBERS, 50_000)

    def test_lock_released_when_service_raises(self) -> None:
        self.assertTrue(guild_sync_lock("111"))
        client = APIClient(raise_request_exception=False)
        with mock.patch(
            "user.internal.discord_names.apply_guild_member_names",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.post(BULK_URL, self._body(), format="json", **HEADERS)
        self.assertEqual(resp.status_code, 500)
        self.assertTrue(guild_sync_lock("111"))


class ClientWrapperTest(TestCase):
    def test_targets_returns_empty_on_failure(self) -> None:
        with mock.patch.object(internal_client.transport, "get", return_value=None):
            self.assertEqual(internal_client.list_discord_name_sync_targets(), [])

    def test_targets_passes_params(self) -> None:
        resp = mock.Mock(ok=True)
        resp.json.return_value = [{"org_id": 1, "guild_id": "111"}]
        with mock.patch.object(
            internal_client.transport, "get", return_value=resp
        ) as get:
            rows = internal_client.list_discord_name_sync_targets(
                scope="all", org_id=5, lock=True
            )
        self.assertEqual(rows, [{"org_id": 1, "guild_id": "111"}])
        get.assert_called_once_with(
            "/orgs/discord-name-sync-targets/",
            params={"scope": "all", "org_id": 5, "lock": 1},
        )

    def test_targets_omits_org_and_lock_when_unset(self) -> None:
        resp = mock.Mock(ok=True)
        resp.json.return_value = []
        with mock.patch.object(
            internal_client.transport, "get", return_value=resp
        ) as get:
            internal_client.list_discord_name_sync_targets(lock=False)
        get.assert_called_once_with(
            "/orgs/discord-name-sync-targets/", params={"scope": "active"}
        )

    def test_targets_returns_empty_on_bad_status_or_json(self) -> None:
        bad = mock.Mock(ok=False)
        with mock.patch.object(internal_client.transport, "get", return_value=bad):
            self.assertEqual(internal_client.list_discord_name_sync_targets(), [])
        broken = mock.Mock(ok=True, text="x")
        broken.json.side_effect = ValueError
        with mock.patch.object(internal_client.transport, "get", return_value=broken):
            self.assertEqual(internal_client.list_discord_name_sync_targets(), [])

    def test_bulk_update_returns_none_on_failure(self) -> None:
        with mock.patch.object(internal_client.transport, "post", return_value=None):
            self.assertIsNone(
                internal_client.bulk_update_member_names(
                    "111", [1], [], complete=True, fetched_at=1.0
                )
            )

    def test_bulk_update_posts_body(self) -> None:
        resp = mock.Mock(ok=True)
        counts = {"users_updated": 1, "org_users_updated": 0, "org_users_cleared": 0}
        resp.json.return_value = counts
        members = [
            {"discord_id": "42", "username": "u", "nick": None, "global_name": None}
        ]
        with mock.patch.object(
            internal_client.transport, "post", return_value=resp
        ) as post:
            result = internal_client.bulk_update_member_names(
                "111", [1, 2], members, complete=True, fetched_at=2.5
            )
        self.assertEqual(result, counts)
        post.assert_called_once_with(
            "/discord/member-names/bulk-update/",
            {
                "guild_id": "111",
                "org_ids": [1, 2],
                "complete": True,
                "fetched_at": 2.5,
                "members": members,
            },
        )
