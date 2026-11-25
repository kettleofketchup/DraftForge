from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from org.api_tokens.sync import sync_mmrs
from org.api_tokens.tokens import hash_secret, issue_token
from org.features import FeatureKey, set_org_feature
from org.mmr import get_org_mmr, set_org_mmr
from org.models import (
    MmrChangeRequest,
    Organization,
    OrgApiLimits,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgLog,
    OrgUser,
    OrgUserGameMmr,
)
from org.tests.mmr_request_mixin import MmrRequestTestMixin

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STEAM_BASE = CustomUser.STEAM_ID_64_BASE


@override_settings(CACHES=LOCMEM_CACHE)
class ApiTokenBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.org = Organization.objects.create(name="Sync Org")
        self.other_org = Organization.objects.create(name="Other Org")
        self.admin = CustomUser.objects.create_user(username="admin", password="x")
        self.staff = CustomUser.objects.create_user(username="staff", password="x")
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.site_admin = CustomUser.objects.create_user(
            username="site", password="x", is_staff=True
        )
        self.admin2 = CustomUser.objects.create_user(username="admin2", password="x")
        self.org.admins.add(self.admin, self.admin2)
        self.org.staff.add(self.staff)
        self.alice = CustomUser.objects.create_user(
            username="alice", password="x", steam_account_id=1001, discordId="d-alice"
        )
        self.bob = CustomUser.objects.create_user(
            username="bob", password="x", steam_account_id=1002, discordId="d-bob"
        )
        self.outsider = CustomUser.objects.create_user(
            username="out", password="x", steam_account_id=1003
        )
        self.ou_alice = OrgUser.objects.create(user=self.alice, organization=self.org)
        self.ou_bob = OrgUser.objects.create(user=self.bob, organization=self.org)
        OrgUser.objects.create(user=self.member, organization=self.org)
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=True, actor=None)

    def bearer(self, raw: str) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
        return client

    def sync_url(self, org: Organization | None = None) -> str:
        return f"/api/organizations/{(org or self.org).pk}/mmr-sync/"


class TokenManagementTests(ApiTokenBase):
    def test_admin_creates_token_secret_shown_once_and_hashed(self) -> None:
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "bot"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        raw = resp.data["token"]
        self.assertTrue(raw.startswith("dfk_"))
        token = OrgApiToken.objects.get(pk=resp.data["id"])
        self.assertEqual(token.user, self.admin)
        self.assertEqual(token.secret_hash, hash_secret(raw.split("_", 2)[2]))
        self.assertEqual(resp.data["operations"], ["mmr:read", "mmr:write"])
        listed = self.client.get(f"/api/organizations/{self.org.pk}/api-tokens/")
        self.assertNotIn("token", listed.data[0])
        self.assertEqual(listed.data[0]["operations"], ["mmr:read", "mmr:write"])
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org, action="create_api_token"
            ).exists()
        )

    def test_staff_and_member_cannot_manage(self) -> None:
        url = f"/api/organizations/{self.org.pk}/api-tokens/"
        for user in (self.staff, self.member):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.post(url, {"name": "x"}, format="json").status_code, 403
            )
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.get(f"{url}usage/").status_code, 403)

    def test_create_blocked_when_feature_off(self) -> None:
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "feature_locked")

    def test_admin_lists_and_revokes_any_org_token(self) -> None:
        mine = issue_token(self.org, self.admin, "mine").token
        theirs = issue_token(self.org, self.admin2, "theirs").token
        issue_token(self.other_org, self.admin2, "elsewhere")
        url = f"/api/organizations/{self.org.pk}/api-tokens/"
        self.client.force_authenticate(self.admin)
        names = {t["name"] for t in self.client.get(url).data}
        self.assertEqual(names, {"mine", "theirs"})
        self.assertEqual(self.client.delete(f"{url}{theirs.pk}/").status_code, 200)
        theirs.refresh_from_db()
        self.assertEqual(theirs.revoked_by, self.admin)
        self.assertIsNone(OrgApiToken.objects.get(pk=mine.pk).revoked_at)


class TokenAuthTests(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.issued = issue_token(self.org, self.admin, "bot")

    def test_get_members(self) -> None:
        resp = self.bearer(self.issued.raw).get(self.sync_url())
        self.assertEqual(resp.status_code, 200)
        steam_ids = {m["steam_id"] for m in resp.data["members"]}
        self.assertIn(1001, steam_ids)
        self.assertNotIn(1003, steam_ids)

    def test_no_token_401(self) -> None:
        self.assertEqual(APIClient().get(self.sync_url()).status_code, 401)

    def test_session_auth_not_accepted(self) -> None:
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.sync_url()).status_code, 401)

    def test_wrong_secret_401(self) -> None:
        bad = f"dfk_{self.issued.token.prefix}_nope"
        self.assertEqual(self.bearer(bad).get(self.sync_url()).status_code, 401)

    def test_revoked_401(self) -> None:
        self.issued.token.revoked_at = timezone.now()
        self.issued.token.save()
        self.assertEqual(
            self.bearer(self.issued.raw).get(self.sync_url()).status_code, 401
        )

    def test_other_org_404(self) -> None:
        resp = self.bearer(self.issued.raw).get(self.sync_url(self.other_org))
        self.assertEqual(resp.status_code, 404)

    def test_feature_off_403(self) -> None:
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        resp = self.bearer(self.issued.raw).get(self.sync_url())
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "feature_locked")

    def test_owner_losing_admin_role_403(self) -> None:
        self.org.admins.remove(self.admin)
        resp = self.bearer(self.issued.raw).get(self.sync_url())
        self.assertEqual(resp.status_code, 403)


class SyncTests(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.raw = issue_token(self.org, self.admin, "bot").raw

    def post(self, body: dict) -> object:
        return self.bearer(self.raw).post(self.sync_url(), body, format="json")

    def test_sync_matches_steam32_steam64_discord(self) -> None:
        set_org_mmr(self.ou_bob, GameType.DOTA2, 3000, mark_verified=False)
        resp = self.post(
            {
                "entries": [
                    {"steam_id": 1001, "mmr": 4200},
                    {"steam_id": STEAM_BASE + 1002, "mmr": 3000},
                    {"discord_id": "d-nobody", "mmr": 1},
                    {"steam_id": 1003, "mmr": 5000},
                    {"steam_id": "abc", "mmr": 5},
                    {"discord_id": "d-alice", "mmr": 99999},
                ]
            }
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["updated"], 1)
        self.assertEqual(resp.data["unchanged"], 1)
        self.assertEqual([u["index"] for u in resp.data["unmatched"]], [2, 3])
        self.assertEqual(sorted(i["index"] for i in resp.data["invalid"]), [4, 5])
        self.ou_alice.refresh_from_db()
        self.assertEqual(
            get_org_mmr(
                OrgUser.objects.nocache()
                .prefetch_related("game_mmrs")
                .get(pk=self.ou_alice.pk),
                GameType.DOTA2,
            ),
            4200,
        )
        self.assertTrue(self.ou_alice.has_active_dota_mmr)
        log = OrgLog.objects.get(action="set_mmr", target_user=self.alice)
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.details["source"], "api_sync")

    def test_duplicate_and_conflicting_entries_invalid(self) -> None:
        resp = self.post(
            {
                "entries": [
                    {"steam_id": 1001, "mmr": 10},
                    {"discord_id": "d-alice", "mmr": 20},
                    {"steam_id": 1001, "discord_id": "d-bob", "mmr": 30},
                ]
            }
        )
        self.assertEqual(resp.data["updated"], 1)
        self.assertEqual(sorted(i["index"] for i in resp.data["invalid"]), [1, 2])

    def test_null_mmr_clears(self) -> None:
        set_org_mmr(self.ou_alice, GameType.DOTA2, 3000, mark_verified=False)
        resp = self.post({"entries": [{"steam_id": 1001, "mmr": None}]})
        self.assertEqual(resp.data["updated"], 1)
        fresh = (
            OrgUser.objects.nocache()
            .prefetch_related("game_mmrs")
            .get(pk=self.ou_alice.pk)
        )
        self.assertEqual(get_org_mmr(fresh, GameType.DOTA2), 0)

    def test_too_many_entries_400(self) -> None:
        resp = self.post({"entries": [{"steam_id": 1001, "mmr": 1}] * 501})
        self.assertEqual(resp.status_code, 400)


class SyncOfficialTests(MmrRequestTestMixin, ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.raw = issue_token(self.org, self.admin, "official").raw

    def _post(
        self, entries: list[dict[str, Any]], *, verified: bool = True
    ) -> Response:
        return self.bearer(self.raw).post(
            self.sync_url(),
            {"entries": entries, "mark_verified": verified},
            format="json",
        )

    def _row(self, org_user: OrgUser) -> OrgUserGameMmr:
        return OrgUserGameMmr.objects.nocache().get(
            org_user=org_user, game_type=GameType.DOTA2
        )

    def test_token_owner_is_verifier_and_pending_request_is_superseded(self) -> None:
        pending = self.make_request(org_user=self.ou_alice)

        response = self._post([{"steam_id": 1001, "mmr": 4200}])

        self.assertEqual(response.status_code, 200, response.data)
        row = self._row(self.ou_alice)
        self.assertEqual(row.mmr, 4200)
        self.assertIsNotNone(row.verified_at)
        self.assertEqual(row.verified_by_id, self.admin.pk)
        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.SUPERSEDED)
        self.assertEqual(pending.reviewed_by_id, self.admin.pk)
        self.assertEqual(pending.approved_mmr, 4200)
        entry = OrgLog.objects.get(action="set_mmr", target_user=self.alice)
        self.assertEqual(entry.actor_id, self.admin.pk)
        self.assertEqual(entry.details["source"], "api_sync")
        self.assertTrue(entry.details["verified"])

    def test_unchanged_value_is_verified_and_supersedes_pending(self) -> None:
        set_org_mmr(self.ou_alice, GameType.DOTA2, 3000, mark_verified=False)
        pending = self.make_request(org_user=self.ou_alice)

        response = self._post([{"steam_id": 1001, "mmr": 3000}])

        self.assertEqual(response.data["unchanged"], 1)
        self.assertEqual(response.data["updated"], 0)
        self.assertEqual(self._row(self.ou_alice).verified_by_id, self.admin.pk)
        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.SUPERSEDED)
        self.assertEqual(pending.approved_mmr, 3000)
        self.assertFalse(OrgLog.objects.filter(action="set_mmr").exists())

    def test_self_entry_rejected_without_blocking_other_members(self) -> None:
        self.admin.discordId = "d-admin"
        self.admin.save(update_fields=["discordId"])
        own_membership = OrgUser.objects.create(user=self.admin, organization=self.org)

        response = self._post(
            [{"discord_id": "d-admin", "mmr": 5000}, {"steam_id": 1001, "mmr": 4200}]
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual([entry["index"] for entry in response.data["invalid"]], [0])
        self.assertFalse(
            OrgUserGameMmr.objects.filter(org_user=own_membership).exists()
        )
        self.assertEqual(self._row(self.ou_alice).verified_by_id, self.admin.pk)
        self.assertFalse(
            OrgLog.objects.filter(action="set_mmr", target_user=self.admin).exists()
        )

    def test_staff_subject_rejected_for_plain_staff_but_member_processed(self) -> None:
        self.org.staff.add(self.bob)

        result = sync_mmrs(
            self.org,
            self.staff,
            [{"steam_id": 1002, "mmr": 5000}, {"steam_id": 1001, "mmr": 4200}],
        )

        self.assertEqual(result.updated, 1)
        self.assertEqual([entry["index"] for entry in result.invalid], [0])
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=self.ou_bob).exists())
        self.assertEqual(self._row(self.ou_alice).verified_by_id, self.staff.pk)

    def test_org_admin_can_verify_staff_subject(self) -> None:
        self.org.staff.add(self.bob)

        response = self._post([{"steam_id": 1002, "mmr": 4200}])

        self.assertEqual(response.data["invalid"], [])
        self.assertEqual(self._row(self.ou_bob).verified_by_id, self.admin.pk)

    def test_superuser_can_verify_own_entry(self) -> None:
        self.admin.is_superuser = True
        self.admin.discordId = "d-admin"
        self.admin.save(update_fields=["is_superuser", "discordId"])
        own_membership = OrgUser.objects.create(user=self.admin, organization=self.org)

        response = self._post([{"discord_id": "d-admin", "mmr": 5000}])

        self.assertEqual(response.data["invalid"], [])
        self.assertEqual(self._row(own_membership).verified_by_id, self.admin.pk)

    def test_unverified_bulk_write_clears_official_metadata_without_superseding(
        self,
    ) -> None:
        set_org_mmr(
            self.ou_alice,
            GameType.DOTA2,
            3000,
            mark_verified=True,
            verified_by=self.admin,
        )
        pending = self.make_request(org_user=self.ou_alice)

        response = self._post([{"steam_id": 1001, "mmr": 4200}], verified=False)

        self.assertEqual(response.data["updated"], 1)
        row = self._row(self.ou_alice)
        self.assertEqual(row.mmr, 4200)
        self.assertIsNone(row.verified_at)
        self.assertIsNone(row.verified_by_id)
        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(
            OrgLog.objects.filter(action="set_mmr", target_user=self.alice).count(), 1
        )


class ThrottleAndUsageTests(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.issued = issue_token(self.org, self.admin, "bot")

    def test_per_minute_limit_429_and_counted(self) -> None:
        OrgApiLimits.objects.create(organization=self.org, per_minute=2, per_day=100)
        client = self.bearer(self.issued.raw)
        codes = [client.get(self.sync_url()).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        usage = OrgApiTokenUsage.objects.get(token=self.issued.token)
        self.assertEqual((usage.request_count, usage.throttled_count), (2, 1))
        self.assertEqual(usage.user, self.admin)

    def test_per_day_limit_429_with_retry_after(self) -> None:
        OrgApiLimits.objects.create(organization=self.org, per_minute=100, per_day=1)
        client = self.bearer(self.issued.raw)
        self.assertEqual(client.get(self.sync_url()).status_code, 200)
        resp = client.get(self.sync_url())
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)

    def test_last_used_at_set(self) -> None:
        self.bearer(self.issued.raw).get(self.sync_url())
        self.issued.token.refresh_from_db()
        self.assertIsNotNone(self.issued.token.last_used_at)

    def test_usage_endpoint_per_user(self) -> None:
        other_raw = issue_token(self.org, self.admin2, "adm2").raw
        self.bearer(self.issued.raw).get(self.sync_url())
        self.bearer(other_raw).get(self.sync_url())
        self.bearer(other_raw).get(self.sync_url())
        OrgApiTokenUsage.objects.create(
            token=self.issued.token,
            organization=self.org,
            user=self.admin,
            date=timezone.now().date() - timedelta(days=60),
            request_count=50,
        )
        self.client.force_authenticate(self.admin)
        data = self.client.get(
            f"/api/organizations/{self.org.pk}/api-tokens/usage/"
        ).data
        totals = {u["user"]["username"]: u["requests"] for u in data["users"]}
        self.assertEqual(totals, {"admin2": 2, "admin": 1})

    def test_limits_put_site_admin_only(self) -> None:
        url = f"/api/organizations/{self.org.pk}/api-limits/"
        body = {"per_minute": 10, "per_day": 20}
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.put(url, body, format="json").status_code, 403)
        self.client.force_authenticate(self.site_admin)
        self.assertEqual(self.client.put(url, body, format="json").status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(url).data, body)
