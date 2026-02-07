"""Tests for CSV import endpoints."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, PositionsModel
from org.models import OrgUser


class OrgCSVImportTest(TestCase):
    """Test POST /api/organizations/{id}/import-csv/"""

    def setUp(self):
        pos = PositionsModel.objects.create()
        self.admin = CustomUser.objects.create_user(
            username="admin", password="pass", positions=pos
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/import-csv/"

    def test_import_creates_org_user_by_steam_id(self):
        """Row with steam_friend_id matching existing user creates OrgUser."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="steamuser",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345678", "base_mmr": 5000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 5000)

    def test_import_creates_stub_user_when_no_match(self):
        """Row with unknown steam_friend_id creates a stub user + OrgUser."""
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999", "base_mmr": 3000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)
        self.assertEqual(resp.data["summary"]["added"], 1)
        user = CustomUser.objects.get(steamid=76561198099999999)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 3000)

    def test_import_by_discord_id(self):
        """Row with discord_id matching existing user creates OrgUser."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="discorduser",
            password="pass",
            positions=pos,
            discordId="123456789012345678",
        )
        resp = self.client.post(
            self.url,
            {"rows": [{"discord_id": "123456789012345678", "base_mmr": 4000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 4000)

    def test_import_skips_existing_member(self):
        """Row matching a user already in the org is skipped."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="existing",
            password="pass",
            positions=pos,
            steamid=76561198011111111,
        )
        OrgUser.objects.create(user=user, organization=self.org, mmr=1000)
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198011111111", "base_mmr": 2000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["skipped"], 1)
        # MMR should NOT be updated for skipped users
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 1000)

    def test_import_row_with_no_identifier_errors(self):
        """Row without steam_friend_id or discord_id reports error."""
        resp = self.client.post(self.url, {"rows": [{"base_mmr": 5000}]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["errors"], 1)
        self.assertIn("No identifier", resp.data["results"][0]["reason"])

    def test_import_conflict_detection(self):
        """Row with steam + discord where existing user has different discord flags warning."""
        pos = PositionsModel.objects.create()
        CustomUser.objects.create_user(
            username="conflictuser",
            password="pass",
            positions=pos,
            steamid=76561198022222222,
            discordId="999999999999999999",
        )
        resp = self.client.post(
            self.url,
            {
                "rows": [
                    {
                        "steam_friend_id": "76561198022222222",
                        "discord_id": "111111111111111111",
                        "base_mmr": 4000,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Should still add the user but include a warning
        self.assertEqual(resp.data["summary"]["added"], 1)
        result = resp.data["results"][0]
        self.assertIn("warning", result)
        self.assertIn("999999999999999999", result["warning"])

    def test_import_requires_staff_access(self):
        """Non-staff/non-admin user gets 403."""
        pos = PositionsModel.objects.create()
        nonadmin = CustomUser.objects.create_user(
            username="nonadmin", password="pass", positions=pos
        )
        client = APIClient()
        client.force_authenticate(nonadmin)
        resp = client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_import_allowed_for_staff(self):
        """Org staff (not admin) can import."""
        pos = PositionsModel.objects.create()
        staff_user = CustomUser.objects.create_user(
            username="staff", password="pass", positions=pos
        )
        self.org.staff.add(staff_user)
        client = APIClient()
        client.force_authenticate(staff_user)
        resp = client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999", "base_mmr": 3000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)

    def test_import_rejects_too_many_rows(self):
        """More than MAX_ROWS returns 400."""
        rows = [{"steam_friend_id": str(76561198000000000 + i)} for i in range(501)]
        resp = self.client.post(self.url, {"rows": rows}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_import_rejects_non_list_rows(self):
        """Non-list rows returns 400."""
        resp = self.client.post(self.url, {"rows": "not a list"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_import_empty_rows(self):
        """Empty rows list returns empty summary."""
        resp = self.client.post(self.url, {"rows": []}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 0)

    def test_import_creates_stub_user_from_discord_id_only(self):
        """Row with only discord_id and no match creates a stub user."""
        resp = self.client.post(
            self.url,
            {"rows": [{"discord_id": "555555555555555555", "base_mmr": 2500}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)
        user = CustomUser.objects.get(discordId="555555555555555555")
        self.assertIsNotNone(user)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 2500)
