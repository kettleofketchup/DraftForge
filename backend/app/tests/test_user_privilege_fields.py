from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization
from tests.populate.utils import ensure_org_user


class UserPrivilegeFieldsTests(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(
            username="priv-owner", password="pw"
        )
        self.member = CustomUser.objects.create_user(
            username="priv-member", password="pw"
        )
        self.root = CustomUser.objects.create_superuser(
            username="priv-root", password="pw"
        )
        self.org = Organization.objects.create(name="Privilege Org")
        self.org.admins.add(self.owner)
        ensure_org_user(self.owner, self.org, mmr=3000)
        ensure_org_user(self.member, self.org, mmr=3000)
        self.client = APIClient()

    def _patch(self, actor: CustomUser, target: CustomUser, body: dict) -> int:
        self.client.force_authenticate(user=actor)
        resp = self.client.patch(f"/api/users/{target.pk}/", body, format="json")
        return resp.status_code

    def test_org_staff_cannot_escalate_self(self) -> None:
        status = self._patch(
            self.owner, self.owner, {"is_superuser": True, "is_staff": True}
        )
        self.assertIn(status, (200, 403))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_superuser)
        self.assertFalse(self.owner.is_staff)

    def test_org_staff_cannot_escalate_member(self) -> None:
        status = self._patch(
            self.owner,
            self.member,
            {"is_superuser": True, "is_staff": True, "is_active": False},
        )
        self.assertIn(status, (200, 403))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser)
        self.assertFalse(self.member.is_staff)
        self.assertTrue(self.member.is_active)

    def test_org_staff_can_still_edit_nickname(self) -> None:
        status = self._patch(self.owner, self.member, {"nickname": "x"})
        self.assertEqual(status, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.nickname, "x")

    def test_superuser_can_set_privileges(self) -> None:
        status = self._patch(self.root, self.member, {"is_staff": True})
        self.assertEqual(status, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_staff)
