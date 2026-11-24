"""Tests for steam_account_id collision handling.

`app_customuser.steam_account_id` is unique=True, but neither write path
validated it: the hand-rolled org endpoint called user.save() directly and
the global endpoint's serializer declares steam_account_id explicitly,
which overrides the UniqueValidator ModelSerializer would have generated.
Both therefore surfaced a raw IntegrityError as a 500.

These tests pin the replacement behaviour: a 409 naming the account that
already holds the id, plus a lookup endpoint the edit form calls on blur.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel
from events.services import process_rsvp
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase
from org.models import Organization, OrgUser
from steam.services.account_lookup import SteamLookupRateLimited
from tests.populate.utils import ensure_org_user
from user.steam_accounts import (
    mark_steam_account_verified,
    steam_account_id_conflict_payload,
)

TAKEN_ID = 765353730
FREE_ID = 111222333
ENSURE = "events.eligibility.steam.ensure_steam_account_exists"
LOOKUP_ON = override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)


class SteamAccountIdConflictTests(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="steam-conflict-admin", password="pw"
        )
        self.holder = CustomUser.objects.create(
            username="geo.potter",
            nickname="George Potter",
            steam_account_id=TAKEN_ID,
        )
        self.target = CustomUser.objects.create(
            username="bigbangg1", nickname="bigbang", steam_account_id=765353
        )
        self.org = Organization.objects.create(name="Steam Conflict Org")
        self.org.admins.add(self.admin)
        self.org_user = ensure_org_user(self.target, self.org, mmr=5000)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @property
    def org_url(self) -> str:
        return f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"

    # --- org-scoped endpoint ---

    def test_org_patch_with_taken_steam_account_id_returns_409(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": TAKEN_ID}, format="json"
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_org_patch_conflict_body_names_the_holder(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": TAKEN_ID}, format="json"
        )
        body = resp.json()
        self.assertEqual(body["code"], "steam_account_id_taken")
        self.assertEqual(body["conflict"]["pk"], self.holder.pk)
        self.assertEqual(body["conflict"]["nickname"], "George Potter")
        self.assertEqual(body["conflict"]["username"], "geo.potter")
        self.assertEqual(
            body["error"],
            f"Friend ID {TAKEN_ID} is already assigned to George Potter (@geo.potter).",
        )

    def test_org_patch_conflict_leaves_target_unchanged(self) -> None:
        self.client.patch(self.org_url, {"steam_account_id": TAKEN_ID}, format="json")
        self.target.refresh_from_db()
        self.assertEqual(self.target.steam_account_id, 765353)

    def test_org_patch_with_free_steam_account_id_succeeds(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": FREE_ID}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.steam_account_id, FREE_ID)

    def test_org_patch_re_sending_own_steam_account_id_is_not_a_conflict(self) -> None:
        # A no-op PATCH already returns 400 "No valid fields to update"
        # (pinned by test_org_endpoint_rejects_empty_patch); all that matters
        # here is that a user's own id is never reported as a collision.
        resp = self.client.patch(
            self.org_url, {"steam_account_id": 765353}, format="json"
        )
        self.assertNotEqual(resp.status_code, 409, resp.content)

    def test_clear_really_clears(self) -> None:
        self.assertTrue(
            mark_steam_account_verified(self.target, self.admin, org_id=None)
        )
        resp = self.client.patch(
            self.org_url, {"steam_account_id": None}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        user = CustomUser.objects.get(pk=self.target.pk)
        self.assertIsNone(user.steam_account_id)
        self.assertIsNone(user.steamid)
        self.assertIsNone(user.steam_account_verified_at)
        self.assertIsNone(user.steam_account_verified_by_id)
        self.assertIsNone(user.steam_account_verified_org_id)

    def test_string_id_coerced_to_int(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": " 111222333 "}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        user = CustomUser.objects.get(pk=self.target.pk)
        self.assertEqual(user.steam_account_id, FREE_ID)
        self.assertEqual(user.steamid, FREE_ID + CustomUser.STEAM_ID_64_BASE)

    def test_non_numeric_id_400(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": "abc"}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "invalid_friend_id")
        self.assertEqual(
            CustomUser.objects.get(pk=self.target.pk).steam_account_id, 765353
        )

    # --- global endpoint ---

    def test_global_patch_with_taken_steam_account_id_does_not_500(self) -> None:
        resp = self.client.patch(
            f"/api/users/{self.target.pk}/",
            {"steam_account_id": TAKEN_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_global_patch_with_free_steam_account_id_succeeds(self) -> None:
        resp = self.client.patch(
            f"/api/users/{self.target.pk}/",
            {"steam_account_id": FREE_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_global_patch_re_sending_own_steam_account_id_is_not_a_conflict(
        self,
    ) -> None:
        resp = self.client.patch(
            f"/api/users/{self.target.pk}/",
            {"steam_account_id": 765353},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)


def _org_user_url(org: Organization, org_user: OrgUser) -> str:
    return f"/api/organizations/{org.pk}/users/{org_user.pk}/"


def _reload(user: CustomUser) -> CustomUser:
    return CustomUser.objects.get(pk=user.pk)


@LOOKUP_ON
class OrgUserPatchVerificationTests(EventTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.target = self.make_user()
        self.target_org_user = OrgUser.objects.get(
            user=self.target, organization=self.org
        )
        self.client = APIClient()

    def _patch(self, actor: CustomUser, data: dict[str, Any]) -> Any:
        self.client.force_authenticate(actor)
        return self.client.patch(
            _org_user_url(self.org, self.target_org_user), data, format="json"
        )

    def _untrusted_setup(self) -> tuple[CustomUser, Organization, OrgUser]:
        actor = CustomUser.objects.create_user(username="ov_creator", password="x")
        own_org = Organization.objects.create(name="OV Own Org", owner=actor)
        own_org.admins.add(actor)
        victim_org_user = OrgUser.objects.create(user=self.target, organization=own_org)
        return actor, own_org, victim_org_user

    def test_trusted_staff_change_verifies(self) -> None:
        staff = CustomUser.objects.create_user(username="ov_site_staff", password="x")
        staff.is_staff = True
        staff.save()
        self.org.admins.add(staff)
        with patch(ENSURE) as ensure:
            resp = self._patch(staff, {"steam_account_id": 717171})
        self.assertEqual(resp.status_code, 200, resp.content)
        ensure.assert_not_called()
        user = _reload(self.target)
        self.assertEqual(user.steam_account_id, 717171)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, staff.pk)
        self.assertIsNone(user.steam_account_verified_org_id)

    def test_event_staff_of_self_signup_change_verifies_with_org(self) -> None:
        event = self.make_event(tournament_league=self.league)
        self.assertTrue(process_rsvp(event, self.target, actor=SYSTEM).self_made)
        with patch(ENSURE) as ensure:
            resp = self._patch(self.admin, {"steam_account_id": 727272})
        self.assertEqual(resp.status_code, 200, resp.content)
        ensure.assert_not_called()
        user = _reload(self.target)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, self.admin.pk)
        self.assertEqual(user.steam_account_verified_org_id, self.org.pk)

    def test_untrusted_org_staff_change_unverified_and_prechecked(self) -> None:
        actor, own_org, victim_org_user = self._untrusted_setup()
        self.client.force_authenticate(actor)
        url = _org_user_url(own_org, victim_org_user)
        with patch(ENSURE, return_value=False) as ensure:
            resp = self.client.patch(url, {"steam_account_id": 737373}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "steam_account_not_found")
        self.assertIn("737373", body["error"])
        self.assertEqual(ensure.call_args.kwargs["budget_user"], actor)
        self.assertIsNone(_reload(self.target).steam_account_id)

        with patch(ENSURE, return_value=True):
            resp = self.client.patch(url, {"steam_account_id": 737374}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        user = _reload(self.target)
        self.assertEqual(user.steam_account_id, 737374)
        self.assertFalse(user.steam_account_verified)

    def test_untrusted_org_staff_rate_limited_429(self) -> None:
        actor, own_org, victim_org_user = self._untrusted_setup()
        self.client.force_authenticate(actor)
        with patch(ENSURE, side_effect=SteamLookupRateLimited()):
            resp = self.client.patch(
                _org_user_url(own_org, victim_org_user),
                {"steam_account_id": 747474},
                format="json",
            )
        self.assertEqual(resp.status_code, 429, resp.content)
        self.assertEqual(resp.json()["code"], "steam_lookup_rate_limited")
        self.assertIn("error", resp.json())

    def test_trusted_staff_out_of_range_rejected(self) -> None:
        superuser = CustomUser.objects.create_superuser(
            username="ov_range_super", password="x"
        )
        for raw in (-1, 2**32, "4294967296"):
            with self.subTest(raw=raw):
                resp = self._patch(superuser, {"steam_account_id": raw})
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.json()["code"], "invalid_friend_id")
                user = _reload(self.target)
                self.assertIsNone(user.steam_account_id)
                self.assertFalse(user.steam_account_verified)

    def test_actor_is_target_unverified(self) -> None:
        superuser = CustomUser.objects.create_superuser(
            username="ov_super", password="x"
        )
        own = OrgUser.objects.create(user=superuser, organization=self.org)
        self.client.force_authenticate(superuser)
        with patch(ENSURE, return_value=None) as ensure:
            resp = self.client.patch(
                _org_user_url(self.org, own),
                {"steam_account_id": 757575},
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        ensure.assert_called_once()
        user = _reload(superuser)
        self.assertEqual(user.steam_account_id, 757575)
        self.assertFalse(user.steam_account_verified)

    def test_update_org_user_nickname_only_keeps_verification(self) -> None:
        self.target.steam_account_id = 767676
        self.target.save()
        superuser = CustomUser.objects.create_superuser(
            username="ov_super2", password="x"
        )
        self.assertTrue(
            mark_steam_account_verified(self.target, superuser, org_id=None)
        )
        resp = self._patch(self.admin, {"nickname": "Renamed"})
        self.assertEqual(resp.status_code, 200, resp.content)
        user = _reload(self.target)
        self.assertEqual(user.nickname, "Renamed")
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, superuser.pk)


@LOOKUP_ON
class UserPatchVerificationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.admin = CustomUser.objects.create_superuser(
            username="up-admin", password="pw"
        )
        self.target = CustomUser.objects.create(
            username="up-target", positions=PositionsModel.objects.create()
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _url(self) -> str:
        return f"/api/users/{self.target.pk}/"

    def test_patch_user_trusted_verifies(self) -> None:
        with patch(ENSURE) as ensure:
            resp = self.client.patch(
                self._url(), {"steam_account_id": 818181}, format="json"
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        ensure.assert_not_called()
        user = _reload(self.target)
        self.assertEqual(user.steam_account_id, 818181)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, self.admin.pk)
        self.assertIsNone(user.steam_account_verified_org_id)

    def test_patch_user_cannot_write_verification_fields(self) -> None:
        self.target.steam_account_id = 828282
        self.target.save()
        resp = self.client.patch(
            self._url(),
            {
                "steam_account_verified_at": "2026-01-01T00:00:00Z",
                "steam_account_verified_by": self.admin.pk,
                "steam_account_exists_checked_at": "2026-01-01T00:00:00Z",
                "nickname": "n",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        user = _reload(self.target)
        self.assertIsNone(user.steam_account_verified_at)
        self.assertIsNone(user.steam_account_verified_by_id)
        self.assertIsNone(user.steam_account_exists_checked_at)

    def test_patch_user_untrusted_prechecked_body(self) -> None:
        actor = CustomUser.objects.create_user(username="up-creator", password="x")
        own_org = Organization.objects.create(name="UP Own Org", owner=actor)
        own_org.admins.add(actor)
        OrgUser.objects.create(user=self.target, organization=own_org)
        self.client.force_authenticate(actor)
        with patch(ENSURE, return_value=False) as ensure:
            resp = self.client.patch(
                self._url(), {"steam_account_id": 838383}, format="json"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "steam_account_not_found")
        self.assertIn("838383", body["steam_account_id"][0])
        self.assertEqual(ensure.call_args.kwargs["budget_user"], actor)
        self.assertIsNone(_reload(self.target).steam_account_id)

        with patch(ENSURE, side_effect=SteamLookupRateLimited()):
            resp = self.client.patch(
                self._url(), {"steam_account_id": 838384}, format="json"
            )
        self.assertEqual(resp.status_code, 429, resp.content)
        self.assertEqual(resp.json()["code"], "steam_lookup_rate_limited")

        with patch(ENSURE, return_value=True):
            resp = self.client.patch(
                self._url(), {"steam_account_id": 838385}, format="json"
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        user = _reload(self.target)
        self.assertEqual(user.steam_account_id, 838385)
        self.assertFalse(user.steam_account_verified)

    def test_patch_user_float_id_still_prechecked(self) -> None:
        actor = CustomUser.objects.create_user(username="up-float", password="x")
        own_org = Organization.objects.create(name="UP Float Org", owner=actor)
        own_org.admins.add(actor)
        OrgUser.objects.create(user=self.target, organization=own_org)
        OrgUser.objects.create(user=actor, organization=own_org)
        cases: list[tuple[CustomUser, int, Any]] = [
            (actor, self.target.pk, 868686.0),
            (actor, self.target.pk, "868686.0"),
            (actor, actor.pk, 878787.0),
        ]
        for client_user, pk, raw in cases:
            with self.subTest(pk=pk, raw=raw):
                self.client.force_authenticate(client_user)
                with patch(ENSURE, return_value=False) as ensure:
                    resp = self.client.patch(
                        f"/api/users/{pk}/", {"steam_account_id": raw}, format="json"
                    )
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.json()["code"], "steam_account_not_found")
                ensure.assert_called_once()
                self.assertIsNone(CustomUser.objects.get(pk=pk).steam_account_id)

    def test_patch_user_out_of_range_rejected(self) -> None:
        for raw in (-5, 0, 2**32):
            with self.subTest(raw=raw):
                resp = self.client.patch(
                    self._url(), {"steam_account_id": raw}, format="json"
                )
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("steam_account_id", resp.json())
                user = _reload(self.target)
                self.assertIsNone(user.steam_account_id)
                self.assertFalse(user.steam_account_verified)

    def test_create_user_by_staff_verifies(self) -> None:
        with patch(ENSURE) as ensure:
            resp = self.client.post(
                "/api/user/register",
                {"username": "up-created", "steam_account_id": 848484},
                format="json",
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        ensure.assert_not_called()
        user = CustomUser.objects.get(username="up-created")
        self.assertEqual(user.steam_account_id, 848484)
        self.assertEqual(user.steamid, 848484 + CustomUser.STEAM_ID_64_BASE)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, self.admin.pk)


@LOOKUP_ON
class AdminLookupBudgetTest(TransactionTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_untrusted_admin_lookups_charge_actor_budget(self) -> None:
        actor = CustomUser.objects.create_user(username="bud-actor", password="x")
        victim = CustomUser.objects.create_user(username="bud-victim", password="x")
        org = Organization.objects.create(name="Budget Org", owner=actor)
        org.admins.add(actor)
        org_user = OrgUser.objects.create(user=victim, organization=org)
        client = APIClient()
        client.force_authenticate(actor)
        api = MagicMock()
        api.return_value.get_player_summaries.return_value = {
            "response": {"players": [{"steamid": "x"}]}
        }
        statuses: list[int] = []
        with patch("steam.services.account_lookup.SteamAPI", api):
            for i in range(11):
                resp = client.patch(
                    _org_user_url(org, org_user),
                    {"steam_account_id": 900_000 + i},
                    format="json",
                )
                statuses.append(resp.status_code)
            self.assertEqual(statuses, [200] * 10 + [429], statuses)
            self.assertEqual(resp.json()["code"], "steam_lookup_rate_limited")

            client.force_authenticate(_reload(victim))
            resp = client.post(
                "/api/profile_update", {"steam_account_id": 950_000}, format="json"
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(_reload(victim).steam_account_id, 950_000)


class SteamAccountIdLookupTests(TestCase):
    def setUp(self) -> None:
        self.viewer = CustomUser.objects.create_user(
            username="lookup-viewer", password="pw"
        )
        self.holder = CustomUser.objects.create(
            username="geo.potter",
            nickname="George Potter",
            steam_account_id=TAKEN_ID,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def url(self, steam_account_id: int) -> str:
        return f"/api/users/steam-account-id/{steam_account_id}/"

    def test_lookup_returns_holder_identity_for_taken_id(self) -> None:
        resp = self.client.get(self.url(TAKEN_ID))
        self.assertEqual(resp.status_code, 200, resp.content)
        holder = resp.json()["holder"]
        self.assertEqual(holder["pk"], self.holder.pk)
        self.assertEqual(holder["nickname"], "George Potter")
        self.assertEqual(holder["username"], "geo.potter")

    def test_lookup_returns_null_holder_for_free_id(self) -> None:
        resp = self.client.get(self.url(FREE_ID))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["holder"])

    def test_lookup_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.url(TAKEN_ID))
        self.assertIn(resp.status_code, (401, 403))


class SteamAccountIdConflictLabelTests(TestCase):
    def test_global_name_without_site_nickname(self) -> None:
        user = CustomUser.objects.create(username="dc", discordNickname="Gwaihir")
        body = steam_account_id_conflict_payload(1, user)
        self.assertEqual(body["conflict"]["discordNickname"], "Gwaihir")
        self.assertEqual(
            body["error"], "Friend ID 1 is already assigned to Gwaihir (@dc)."
        )

    def test_global_name_before_site_nickname(self) -> None:
        user = CustomUser.objects.create(
            username="dc", nickname="Site", discordNickname="Gwaihir"
        )
        body = steam_account_id_conflict_payload(1, user)
        self.assertEqual(
            body["error"], "Friend ID 1 is already assigned to Gwaihir (@dc)."
        )

    def test_site_nickname_without_global_name(self) -> None:
        user = CustomUser.objects.create(username="dc", nickname="Site")
        body = steam_account_id_conflict_payload(1, user)
        self.assertEqual(
            body["error"], "Friend ID 1 is already assigned to Site (@dc)."
        )

    def test_steam_only_holder(self) -> None:
        user = CustomUser.objects.create(username=None)
        body = steam_account_id_conflict_payload(1, user)
        self.assertEqual(
            body["error"], f"Friend ID 1 is already assigned to User {user.pk}."
        )

    def test_omits_redundant_username(self) -> None:
        user = CustomUser.objects.create(username="plainuser")
        body = steam_account_id_conflict_payload(2, user)
        self.assertEqual(body["error"], "Friend ID 2 is already assigned to plainuser.")
