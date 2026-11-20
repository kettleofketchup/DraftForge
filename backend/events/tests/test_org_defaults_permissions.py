from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import OrgEventDefaults
from events.tests.base import EventTestCase


class OrgEventDefaultsPermissionTests(EventTestCase):
    """PATCH needs org admin access; GET stays open to any authenticated user."""

    client: APIClient  # type: ignore[assignment]

    def setUp(self) -> None:
        self.client = APIClient()
        self.defaults, _ = OrgEventDefaults.objects.get_or_create(organization=self.org)
        self.url = f"/api/events/defaults/{self.defaults.pk}/"
        self.staff = CustomUser.objects.create_user(
            username="defaults_staff", password="testpass"
        )
        self.org.staff.add(self.staff)
        self.org_admin = CustomUser.objects.create_user(
            username="defaults_org_admin", password="testpass"
        )
        self.org.admins.add(self.org_admin)
        self.site_admin = CustomUser.objects.create_user(
            username="defaults_site_admin", password="testpass", is_staff=True
        )

    def _patch(self, user: CustomUser) -> Response:
        self.client.force_authenticate(user=user)
        return self.client.patch(self.url, {"max_players": 12}, format="json")

    def test_org_staff_cannot_patch(self) -> None:
        resp = self._patch(self.staff)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.defaults.refresh_from_db()
        self.assertNotEqual(self.defaults.max_players, 12)

    def test_org_admin_can_patch(self) -> None:
        self.assertEqual(self._patch(self.org_admin).status_code, 200)
        self.defaults.refresh_from_db()
        self.assertEqual(self.defaults.max_players, 12)

    def test_org_owner_can_patch(self) -> None:
        self.assertEqual(self._patch(self.admin).status_code, 200)

    def test_site_admin_can_patch(self) -> None:
        self.assertEqual(self._patch(self.site_admin).status_code, 200)

    def test_unrelated_user_cannot_patch(self) -> None:
        self.assertEqual(self._patch(self.unrelated_user).status_code, 403)

    def test_org_staff_can_still_read(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get("/api/events/defaults/", {"organization": self.org.pk})
        self.assertEqual(resp.status_code, 200, resp.content)
