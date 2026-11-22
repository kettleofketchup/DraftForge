from unittest import mock

import redis
from cacheops.conf import settings as cacheops_settings
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Tournament
from discordbot.services.member_names import MemberNames
from league.models import League
from org import discord_names
from org.discord_names import (
    NameSyncResult,
    apply_guild_member_names,
    org_ids_for_guild,
)
from org.models import Organization, OrgUser

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_discord_names",
    }
}

ZERO = NameSyncResult(0, 0, 0)


def _dragon(
    nick: str | None = "DragonClaw",
    global_name: str | None = "GwaihirTheWindlord",
    username: str | None = "dc_new",
) -> MemberNames:
    return MemberNames("42", username, nick, global_name)


@override_settings(CACHES=LOCMEM)
class ApplyGuildMemberNamesTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.org_a = Organization.objects.create(
            name="Guild A1", discord_server_id="111"
        )
        self.org_b = Organization.objects.create(
            name="Guild A2", discord_server_id="111"
        )
        self.org_c = Organization.objects.create(
            name="Guild C", discord_server_id="222"
        )
        self.user = CustomUser.objects.create(
            username="dragonclaw_site", discordId="42", discordUsername="dc_old"
        )
        self.user.nickname = "MySite"
        self.user.save()
        self.ou_a = OrgUser.objects.create(user=self.user, organization=self.org_a)
        self.ou_b = OrgUser.objects.create(user=self.user, organization=self.org_b)
        self.ou_c = OrgUser.objects.create(
            user=self.user, organization=self.org_c, guild_nickname="OtherGuildNick"
        )

    def _apply(
        self,
        members: list[MemberNames],
        *,
        org_ids: list[int] | None = None,
        complete: bool = True,
        fetched_at: float | None = None,
    ) -> NameSyncResult:
        with self.captureOnCommitCallbacks(execute=True):
            return apply_guild_member_names(
                "111",
                org_ids if org_ids is not None else [self.org_a.pk, self.org_b.pk],
                members,
                complete=complete,
                fetched_at=fetched_at,
            )

    def test_updates_global_name_username_and_nick(self) -> None:
        result = self._apply([_dragon()])
        self.user.refresh_from_db()
        self.assertEqual(self.user.discordNickname, "GwaihirTheWindlord")
        self.assertEqual(self.user.discordUsername, "dc_new")
        self.assertEqual(self.user.username, "dragonclaw_site")
        self.assertEqual(CustomUser.objects.get(pk=self.user.pk).nickname, "MySite")
        for ou in (self.ou_a, self.ou_b):
            ou.refresh_from_db()
            self.assertEqual(ou.guild_nickname, "DragonClaw")
        self.assertEqual(result, NameSyncResult(1, 2, 0))
        self.assertEqual(
            result.as_dict(),
            {"users_updated": 1, "org_users_updated": 2, "org_users_cleared": 0},
        )

    def test_foreign_guild_org_ids_dropped(self) -> None:
        self._apply([_dragon()], org_ids=[self.org_a.pk, self.org_c.pk])
        self.ou_c.refresh_from_db()
        self.assertEqual(self.ou_c.guild_nickname, "OtherGuildNick")
        self.ou_a.refresh_from_db()
        self.assertEqual(self.ou_a.guild_nickname, "DragonClaw")

    def test_departure_clears_only_when_complete(self) -> None:
        self._apply([_dragon()])
        other = MemberNames("7", "someone", "Someone", None)
        self._apply([other], complete=False)
        self.ou_a.refresh_from_db()
        self.assertEqual(self.ou_a.guild_nickname, "DragonClaw")
        result = self._apply([other], org_ids=[self.org_a.pk], complete=True)
        self.ou_a.refresh_from_db()
        self.assertIsNone(self.ou_a.guild_nickname)
        self.assertEqual(result.org_users_cleared, 1)

    def test_member_without_discord_id_never_cleared(self) -> None:
        local = CustomUser.objects.create(username="no_discord")
        ou = OrgUser.objects.create(
            user=local, organization=self.org_a, guild_nickname="Kept"
        )
        self._apply([_dragon()], complete=True)
        ou.refresh_from_db()
        self.assertEqual(ou.guild_nickname, "Kept")

    def test_empty_complete_list_never_clears(self) -> None:
        self.ou_a.guild_nickname = "DragonClaw"
        self.ou_a.save()
        result = self._apply([], complete=True)
        self.assertEqual(result, ZERO)
        self.ou_a.refresh_from_db()
        self.assertEqual(self.ou_a.guild_nickname, "DragonClaw")

    def test_none_global_name_overwrites(self) -> None:
        self._apply([_dragon()])
        self._apply([_dragon(global_name=None)])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.discordNickname)

    def test_empty_username_does_not_overwrite_discordUsername(self) -> None:
        self._apply([_dragon(username=None)])
        self.user.refresh_from_db()
        self.assertEqual(self.user.discordUsername, "dc_old")
        self._apply([_dragon(username="")])
        self.user.refresh_from_db()
        self.assertEqual(self.user.discordUsername, "dc_old")

    def test_blank_nick_normalises_to_none(self) -> None:
        self._apply([_dragon()])
        self._apply([_dragon(nick="   ")])
        self.ou_a.refresh_from_db()
        self.assertIsNone(self.ou_a.guild_nickname)

    def test_unchanged_rows_not_written(self) -> None:
        self._apply([_dragon()])
        with CaptureQueriesContext(connection) as ctx:
            result = self._apply([_dragon()])
        self.assertEqual(result, ZERO)
        updates = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith("UPDATE")
        ]
        self.assertEqual(updates, [])

    def test_1500_members_no_operational_error(self) -> None:
        CustomUser.objects.bulk_create(
            [
                CustomUser(username=f"bulk_{i}", discordId=str(10_000 + i))
                for i in range(1500)
            ]
        )
        for i in range(3):
            OrgUser.objects.create(
                user=CustomUser.objects.get(discordId=str(10_000 + i)),
                organization=self.org_a,
            )
        members = [
            MemberNames(str(10_000 + i), f"bulk_{i}", f"Nick{i}", f"Global{i}")
            for i in range(1500)
        ]
        result = self._apply(members, org_ids=[self.org_a.pk])
        self.assertEqual(result.users_updated, 1500)
        self.assertEqual(result.org_users_updated, 3)
        self.assertEqual(
            CustomUser.objects.get(discordId="11499").discordNickname, "Global1499"
        )

    def test_out_of_order_complete_snapshot_dropped(self) -> None:
        self._apply([_dragon(nick="Newer")], fetched_at=200.0)
        result = self._apply([_dragon(nick="Older")], fetched_at=100.0)
        self.assertEqual(result, ZERO)
        self.ou_a.refresh_from_db()
        self.assertEqual(self.ou_a.guild_nickname, "Newer")
        self._apply([_dragon(nick="Partial")], complete=False, fetched_at=50.0)
        self.ou_a.refresh_from_db()
        self.assertEqual(self.ou_a.guild_nickname, "Partial")

    def test_applied_snapshot_recorded_only_for_complete(self) -> None:
        self._apply([_dragon()], complete=False, fetched_at=300.0)
        self.assertIsNone(cache.get("discord_name_sync_applied_111"))
        self._apply([_dragon()], complete=True, fetched_at=300.0)
        self.assertEqual(cache.get("discord_name_sync_applied_111"), 300.0)

    def test_large_change_set_uses_model_invalidation(self) -> None:
        other = CustomUser.objects.create(username="other", discordId="43")
        members = [_dragon(), MemberNames("43", "other_dc", None, "OtherGlobal")]
        with (
            mock.patch.object(discord_names, "PER_OBJECT_INVALIDATION_MAX", 2),
            mock.patch.object(discord_names, "invalidate_model") as inv_model,
            mock.patch.object(discord_names, "cacheops_invalidate_obj") as inv_obj,
        ):
            self._apply(members)
        self.assertIsNotNone(other)
        inv_obj.assert_not_called()
        self.assertEqual(
            sorted(c.args[0].__name__ for c in inv_model.call_args_list),
            ["CustomUser", "OrgUser"],
        )

    def test_small_change_set_uses_per_object_invalidation(self) -> None:
        with (
            mock.patch.object(discord_names, "invalidate_model") as inv_model,
            mock.patch.object(discord_names, "cacheops_invalidate_obj") as inv_obj,
            mock.patch.object(discord_names, "log") as log,
        ):
            self._apply([_dragon()])
        inv_model.assert_not_called()
        invalidated = [c.args[0] for c in inv_obj.call_args_list]
        self.assertIn(
            self.ou_a.pk, [o.pk for o in invalidated if isinstance(o, OrgUser)]
        )
        users = [o for o in invalidated if isinstance(o, CustomUser)]
        self.assertEqual(
            {u.discordNickname for u in users}, {None, "GwaihirTheWindlord"}
        )
        summaries = [
            c
            for c in log.info.call_args_list
            if c.args[0] == "name_sync_cache_invalidated"
        ]
        self.assertEqual(len(summaries), 1)


@override_settings(CACHES=LOCMEM)
class OrgIdsForGuildTests(TestCase):
    def test_returns_orgs_on_guild(self) -> None:
        a = Organization.objects.create(name="G1", discord_server_id="111")
        b = Organization.objects.create(name="G2", discord_server_id="111")
        Organization.objects.create(name="G3", discord_server_id="222")
        Organization.objects.create(name="G4", discord_server_id="")
        self.assertEqual(sorted(org_ids_for_guild("111")), sorted([a.pk, b.pk]))
        self.assertEqual(org_ids_for_guild(""), [])


def _cacheops_redis_reachable() -> bool:
    if not cacheops_settings.CACHEOPS_ENABLED or not getattr(
        settings, "CACHEOPS", None
    ):
        return False
    cfg = getattr(settings, "CACHEOPS_REDIS", None)
    if not cfg:
        return False
    try:
        client = redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            db=cfg["db"],
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        return client.ping() is True
    except Exception:
        return False


@override_settings(CACHES=LOCMEM)
class ApplyGuildMemberNamesCacheopsTests(TransactionTestCase):
    def setUp(self) -> None:
        if not _cacheops_redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        cache.clear()
        self.staff = CustomUser.objects.create(username="ns_staff", is_staff=True)
        self.org = Organization.objects.create(
            name="Evict Org", discord_server_id="111"
        )
        self.league = League.objects.create(
            name="Evict Lg", organization=self.org, steam_league_id=54321
        )
        self.tournament = Tournament.objects.create(
            name="Evict T",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )
        self.user = CustomUser.objects.create(
            username="ns_dragon", discordId="42", discordUsername="dc_old"
        )
        self.tournament.users.add(self.user)
        OrgUser.objects.get_or_create(user=self.user, organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def _org_users_nick(self) -> str | None:
        resp = self.client.get(f"/api/organizations/{self.org.pk}/users/")
        self.assertEqual(resp.status_code, 200, resp.content)
        row = next(r for r in resp.json() if r["pk"] == self.user.pk)
        return row["guildNickname"]

    def _tournament_nick(self) -> str | None:
        resp = self.client.get(f"/api/tournaments/{self.tournament.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        users = resp.json()["_users"]
        return users[str(self.user.pk)]["guildNickname"]

    def test_cacheops_eviction_real(self) -> None:
        self.assertIsNone(
            CustomUser.objects.filter(discordId="42").first().discordNickname
        )
        self.assertIsNone(self._org_users_nick())
        self.assertIsNone(self._tournament_nick())
        self.assertIsNone(self._tournament_nick())
        with self.assertNumQueries(0):
            self.assertIsNone(self._tournament_nick())

        apply_guild_member_names("111", [self.org.pk], [_dragon()], complete=True)

        self.assertEqual(
            CustomUser.objects.filter(discordId="42").first().discordNickname,
            "GwaihirTheWindlord",
        )
        self.assertEqual(self._org_users_nick(), "DragonClaw")
        self.assertEqual(self._tournament_nick(), "DragonClaw")
