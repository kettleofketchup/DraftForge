"""The org create/update API must not change owner, admins or staff.

Roles change only through the admin_team endpoints (add/remove admin and
staff, transfer ownership), which enforce owner-only rules and write OrgLog.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, Organization


class OrganizationRoleFieldsTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.admin = CustomUser.objects.create_user(username="admin", password="x")
        self.staff = CustomUser.objects.create_user(username="staff", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )
        self.superuser = CustomUser.objects.create_superuser(
            username="root", password="x"
        )
        self.org = Organization.objects.create(name="Org", owner=self.owner)
        self.org.admins.add(self.owner, self.admin)
        self.org.staff.add(self.staff)
        self.client = APIClient()
        self.url = f"/api/organizations/{self.org.pk}/"

    def _patch_as(self, user: CustomUser, data: dict) -> int:
        self.client.force_authenticate(user=user)
        return self.client.patch(self.url, data, format="json").status_code

    def _assert_roles_unchanged(self) -> None:
        self.org.refresh_from_db()
        self.assertEqual(self.org.owner, self.owner)
        self.assertEqual(
            set(self.org.admins.values_list("pk", flat=True)),
            {self.owner.pk, self.admin.pk},
        )
        self.assertEqual(
            set(self.org.staff.values_list("pk", flat=True)), {self.staff.pk}
        )

    def test_admin_cannot_make_self_owner(self) -> None:
        self._patch_as(self.admin, {"owner_id": self.admin.pk})
        self._assert_roles_unchanged()

    def test_admin_cannot_rewrite_admin_ids(self) -> None:
        self._patch_as(self.admin, {"admin_ids": [self.admin.pk]})
        self._assert_roles_unchanged()

    def test_admin_cannot_rewrite_staff_ids(self) -> None:
        self._patch_as(self.admin, {"staff_ids": [self.outsider.pk]})
        self._assert_roles_unchanged()

    def test_staff_cannot_change_roles(self) -> None:
        code = self._patch_as(
            self.staff,
            {
                "owner_id": self.staff.pk,
                "admin_ids": [self.staff.pk],
                "staff_ids": [],
            },
        )
        self.assertEqual(code, status.HTTP_403_FORBIDDEN)
        self._assert_roles_unchanged()

    def test_owner_cannot_change_owner_via_update(self) -> None:
        self._patch_as(self.owner, {"owner_id": self.admin.pk})
        self._assert_roles_unchanged()

    def test_superuser_cannot_change_roles_via_update(self) -> None:
        self._patch_as(
            self.superuser,
            {
                "owner_id": self.outsider.pk,
                "admin_ids": [self.outsider.pk],
                "staff_ids": [self.outsider.pk],
            },
        )
        self._assert_roles_unchanged()

    def test_put_cannot_change_roles(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(
            self.url,
            {
                "name": "Org",
                "owner_id": self.admin.pk,
                "admin_ids": [self.admin.pk],
                "staff_ids": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_roles_unchanged()

    def test_admin_can_still_edit_name_and_description(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            self.url,
            {
                "name": "Renamed",
                "description": "New description",
                "owner_id": self.admin.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Renamed")
        self.assertEqual(self.org.description, "New description")
        self._assert_roles_unchanged()

    def test_read_output_has_role_objects_not_id_fields(self) -> None:
        data = self.client.get(self.url).data
        self.assertEqual(data["owner"]["pk"], self.owner.pk)
        self.assertEqual(
            {u["pk"] for u in data["admins"]}, {self.owner.pk, self.admin.pk}
        )
        self.assertEqual({u["pk"] for u in data["staff"]}, {self.staff.pk})
        for field in ("owner_id", "admin_ids", "staff_ids"):
            self.assertNotIn(field, data)

    def test_create_ignores_role_fields(self) -> None:
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "Fresh Org",
                "owner_id": self.owner.pk,
                "admin_ids": [self.admin.pk],
                "staff_ids": [self.staff.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        org = Organization.objects.get(name="Fresh Org")
        self.assertEqual(org.owner, self.outsider)
        self.assertEqual(
            list(org.admins.values_list("pk", flat=True)), [self.outsider.pk]
        )
        self.assertFalse(org.staff.exists())
