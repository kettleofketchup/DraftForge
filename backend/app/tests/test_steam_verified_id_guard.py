"""Org staff must not undo another org's (or site staff's) Friend ID verification."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization
from tests.populate.utils import ensure_org_user
from user.steam_accounts import mark_steam_account_verified

VERIFIED_ID = 765353
OTHER_ID = 111222333
ENSURE = "events.eligibility.steam.ensure_steam_account_exists"


@patch(ENSURE, return_value=True)
class VerifiedFriendIdGuardTests(TestCase):
    def setUp(self) -> None:
        self.site_staff = CustomUser.objects.create_superuser(
            username="guard-site-staff", password="pw"
        )
        self.target = CustomUser.objects.create(
            username="guard-target", steam_account_id=VERIFIED_ID
        )
        self.attacker = CustomUser.objects.create(username="guard-attacker")
        self.attacker_org = Organization.objects.create(name="Guard Attacker Org")
        self.attacker_org.admins.add(self.attacker)
        self.attacker_org_user = ensure_org_user(self.target, self.attacker_org)

        self.verifier = CustomUser.objects.create(username="guard-verifier")
        self.verifier_org = Organization.objects.create(name="Guard Verifier Org")
        self.verifier_org.admins.add(self.verifier)
        self.verifier_org_user = ensure_org_user(self.target, self.verifier_org)

        self.client = APIClient()

    def _verify(self, org: Organization | None) -> None:
        actor = self.site_staff if org is None else self.verifier
        self.assertTrue(
            mark_steam_account_verified(
                self.target, actor, org_id=None if org is None else org.pk
            )
        )

    def _org_patch(
        self, actor: CustomUser, org: Organization, org_user_pk: int, new_id: int | None
    ) -> int:
        self.client.force_authenticate(user=actor)
        resp = self.client.patch(
            f"/api/organizations/{org.pk}/users/{org_user_pk}/",
            {"steam_account_id": new_id},
            format="json",
        )
        return resp.status_code

    def _assert_untouched(self) -> None:
        user = CustomUser.objects.get(pk=self.target.pk)
        self.assertEqual(user.steam_account_id, VERIFIED_ID)
        self.assertIsNotNone(user.steam_account_verified_at)

    def test_other_org_cannot_clear_site_staff_verified_id(self, _: MagicMock) -> None:
        self._verify(None)
        code = self._org_patch(
            self.attacker, self.attacker_org, self.attacker_org_user.pk, None
        )
        self.assertEqual(code, 403)
        self._assert_untouched()

    def test_other_org_cannot_change_org_verified_id(self, ensure: MagicMock) -> None:
        self._verify(self.verifier_org)
        self.client.force_authenticate(user=self.attacker)
        resp = self.client.patch(
            f"/api/organizations/{self.attacker_org.pk}/users/"
            f"{self.attacker_org_user.pk}/",
            {"steam_account_id": OTHER_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(resp.json()["code"], "steam_account_verified_elsewhere")
        self.assertIn(self.verifier_org.name, resp.json()["error"])
        ensure.assert_not_called()
        self._assert_untouched()

    def test_global_user_patch_cannot_clear_verified_id(self, _: MagicMock) -> None:
        self._verify(self.verifier_org)
        self.client.force_authenticate(user=self.attacker)
        resp = self.client.patch(
            f"/api/users/{self.target.pk}/",
            {"steam_account_id": None},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self._assert_untouched()

    def test_verifying_org_staff_can_clear(self, _: MagicMock) -> None:
        self._verify(self.verifier_org)
        code = self._org_patch(
            self.verifier, self.verifier_org, self.verifier_org_user.pk, None
        )
        self.assertEqual(code, 200)
        user = CustomUser.objects.get(pk=self.target.pk)
        self.assertIsNone(user.steam_account_id)
        self.assertIsNone(user.steam_account_verified_at)

    def test_site_staff_can_clear(self, _: MagicMock) -> None:
        self._verify(self.verifier_org)
        code = self._org_patch(
            self.site_staff, self.attacker_org, self.attacker_org_user.pk, None
        )
        self.assertEqual(code, 200)
        self.assertIsNone(CustomUser.objects.get(pk=self.target.pk).steam_account_id)

    def test_unverified_id_stays_editable_by_org_staff(self, _: MagicMock) -> None:
        code = self._org_patch(
            self.attacker, self.attacker_org, self.attacker_org_user.pk, OTHER_ID
        )
        self.assertEqual(code, 200)
        self.assertEqual(
            CustomUser.objects.get(pk=self.target.pk).steam_account_id, OTHER_ID
        )
