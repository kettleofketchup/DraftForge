"""Tests for steam_account_id collision handling.

`app_customuser.steam_account_id` is unique=True, but neither write path
validated it: the hand-rolled org endpoint called user.save() directly and
the global endpoint's serializer declares steam_account_id explicitly,
which overrides the UniqueValidator ModelSerializer would have generated.
Both therefore surfaced a raw IntegrityError as a 500.

These tests pin the replacement behaviour: a 409 naming the account that
already holds the id, plus a lookup endpoint the edit form calls on blur.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.models import OrgUser

TAKEN_ID = 765353730
FREE_ID = 111222333


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
        self.org_user = OrgUser.objects.create(
            user=self.target, organization=self.org, mmr=5000
        )
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

    def test_org_patch_clearing_steam_account_id_is_not_a_conflict(self) -> None:
        resp = self.client.patch(
            self.org_url, {"steam_account_id": None}, format="json"
        )
        self.assertNotEqual(resp.status_code, 409, resp.content)

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
