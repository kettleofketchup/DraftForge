"""
Tests pinning partial-PATCH semantics for both the org-scoped and global
user-update endpoints. The edit-user modal sends only dirty fields, so
both endpoints must treat partial nested 'positions' objects as
"update-only-listed-slots", not "replace-whole-positions".

We use TestCase (not TransactionTestCase) here because cacheops auto-
invalidation on post_save fires inside the test's transaction wrapper,
which is fine for these assertions. The optional cache-commit
verification test in Task 2 uses TransactionTestCase because it relies
on transaction.on_commit hooks fired by invalidate_after_commit.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, PositionsModel
from org.models import OrgUser


class PartialUserPatchTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            username="patch-admin", password="pw"
        )
        self.target_positions = PositionsModel.objects.create(
            carry=2, mid=2, offlane=2, soft_support=2, hard_support=2
        )
        self.target = CustomUser.objects.create(
            username="patch-target",
            nickname="Target",
            steam_account_id=12345,
            positions=self.target_positions,
        )
        self.org = Organization.objects.create(name="Patch Test Org")
        self.org.admins.add(self.admin)
        self.org_user = OrgUser.objects.create(
            user=self.target, organization=self.org, mmr=5000
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_partial_positions_patch_via_org_endpoint_does_not_zero_other_slots(self):
        """PATCH {positions: {carry: 1}} must leave mid/offlane/soft_support/hard_support unchanged."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {"positions": {"carry": 1}}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target_positions.refresh_from_db()
        self.assertEqual(self.target_positions.carry, 1)
        self.assertEqual(self.target_positions.mid, 2)
        self.assertEqual(self.target_positions.offlane, 2)
        self.assertEqual(self.target_positions.soft_support, 2)
        self.assertEqual(self.target_positions.hard_support, 2)

    def test_partial_positions_patch_via_global_endpoint_passes_serializer_validation(self):
        """PATCH /users/:pk/ {positions: {carry: 3}} must return 200, not trip required-field validation."""
        url = f"/api/users/{self.target.pk}/"
        resp = self.client.patch(url, {"positions": {"carry": 3}}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target_positions.refresh_from_db()
        self.assertEqual(self.target_positions.carry, 3)
        self.assertEqual(self.target_positions.mid, 2)

    def test_org_endpoint_rejects_empty_patch(self):
        """Pin existing behavior: empty PATCH body returns 400. Frontend has a client-side guard."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_partial_mmr_patch_via_org_endpoint_does_not_clear_nickname(self):
        """PATCH {mmr: 6500} must leave nickname unchanged — proves the safety property
        the spec relies on for concurrent edits."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {"mmr": 6500}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target.refresh_from_db()
        self.org_user.refresh_from_db()
        self.assertEqual(self.org_user.mmr, 6500)
        self.assertEqual(self.target.nickname, "Target")
