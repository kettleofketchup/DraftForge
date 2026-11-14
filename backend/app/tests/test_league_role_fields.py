"""The league create/update API must not change admins, staff or organization.

Roles change only through the admin_team league endpoints, which enforce
org-admin rules for admins and write LeagueLog. A league stays in the
organization it was created in.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization


class LeagueRoleFieldsTest(TestCase):
    def setUp(self) -> None:
        self.org_admin = CustomUser.objects.create_user(
            username="orgadmin", password="x"
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin", password="x"
        )
        self.other_admin = CustomUser.objects.create_user(
            username="otheradmin", password="x"
        )
        self.league_staff = CustomUser.objects.create_user(
            username="leaguestaff", password="x"
        )
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )
        self.superuser = CustomUser.objects.create_superuser(
            username="root", password="x"
        )
        self.org = Organization.objects.create(name="Org")
        self.org.admins.add(self.org_admin)
        self.other_org = Organization.objects.create(
            name="Other Org", owner=self.league_admin
        )
        self.other_org.admins.add(self.league_admin)
        self.league = League.objects.create(organization=self.org, name="League")
        self.league.admins.add(self.league_admin, self.other_admin)
        self.league.staff.add(self.league_staff)
        self.client = APIClient()
        self.url = f"/api/leagues/{self.league.pk}/"

    def _patch_as(self, user: CustomUser, data: dict) -> int:
        self.client.force_authenticate(user=user)
        return self.client.patch(self.url, data, format="json").status_code

    def _assert_roles_unchanged(self) -> None:
        self.league.refresh_from_db()
        self.assertEqual(self.league.organization_id, self.org.pk)
        self.assertEqual(
            set(self.league.admins.values_list("pk", flat=True)),
            {self.league_admin.pk, self.other_admin.pk},
        )
        self.assertEqual(
            set(self.league.staff.values_list("pk", flat=True)),
            {self.league_staff.pk},
        )

    def test_league_admin_cannot_add_admins(self) -> None:
        self._patch_as(
            self.league_admin,
            {
                "admin_ids": [
                    self.league_admin.pk,
                    self.other_admin.pk,
                    self.outsider.pk,
                ]
            },
        )
        self._assert_roles_unchanged()

    def test_league_admin_cannot_remove_other_admins(self) -> None:
        self._patch_as(self.league_admin, {"admin_ids": [self.league_admin.pk]})
        self._assert_roles_unchanged()

    def test_league_admin_cannot_rewrite_staff_ids(self) -> None:
        self._patch_as(self.league_admin, {"staff_ids": [self.outsider.pk]})
        self._assert_roles_unchanged()

    def test_league_admin_cannot_move_league_to_another_org(self) -> None:
        self._patch_as(self.league_admin, {"organization_id": self.other_org.pk})
        self._assert_roles_unchanged()

    def test_org_admin_cannot_change_roles_or_org_via_update(self) -> None:
        self._patch_as(
            self.org_admin,
            {
                "admin_ids": [self.org_admin.pk],
                "staff_ids": [],
                "organization_id": self.other_org.pk,
            },
        )
        self._assert_roles_unchanged()

    def test_superuser_cannot_change_roles_or_org_via_update(self) -> None:
        self._patch_as(
            self.superuser,
            {
                "admin_ids": [self.outsider.pk],
                "staff_ids": [self.outsider.pk],
                "organization_id": self.other_org.pk,
            },
        )
        self._assert_roles_unchanged()

    def test_league_staff_cannot_update(self) -> None:
        code = self._patch_as(
            self.league_staff,
            {"admin_ids": [self.league_staff.pk], "name": "Hijacked"},
        )
        self.assertEqual(code, status.HTTP_403_FORBIDDEN)
        self._assert_roles_unchanged()

    def test_put_cannot_change_roles_or_org(self) -> None:
        self.client.force_authenticate(user=self.league_admin)
        response = self.client.put(
            self.url,
            {
                "name": "League",
                "organization_id": self.other_org.pk,
                "admin_ids": [self.league_admin.pk],
                "staff_ids": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_roles_unchanged()

    def test_league_admin_can_still_edit_league_details(self) -> None:
        self.client.force_authenticate(user=self.league_admin)
        response = self.client.patch(
            self.url,
            {
                "name": "Renamed",
                "description": "New description",
                "rules": "New rules",
                "prize_pool": "$100",
                "steam_league_id": 777,
                "admin_ids": [self.league_admin.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.league.refresh_from_db()
        self.assertEqual(self.league.name, "Renamed")
        self.assertEqual(self.league.description, "New description")
        self.assertEqual(self.league.rules, "New rules")
        self.assertEqual(self.league.prize_pool, "$100")
        self.assertEqual(self.league.steam_league_id, 777)
        self._assert_roles_unchanged()

    def test_read_output_has_role_objects_not_id_fields(self) -> None:
        data = self.client.get(self.url).data
        self.assertEqual(data["organization"]["pk"], self.org.pk)
        self.assertEqual(
            {u["pk"] for u in data["admins"]},
            {self.league_admin.pk, self.other_admin.pk},
        )
        self.assertEqual({u["pk"] for u in data["staff"]}, {self.league_staff.pk})
        for field in ("admin_ids", "staff_ids", "organization_id"):
            self.assertNotIn(field, data)

    def test_outsider_cannot_create_league_in_org_via_organization_id(self) -> None:
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(
            "/api/leagues/",
            {"name": "Sneaky League", "organization_id": self.org.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(League.objects.filter(name="Sneaky League").exists())

    def test_org_admin_can_create_league_with_organization_id(self) -> None:
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/leagues/",
            {
                "name": "Fresh League",
                "organization_id": self.org.pk,
                "description": "",
                "rules": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        league = League.objects.get(name="Fresh League")
        self.assertEqual(league.organization_id, self.org.pk)

    def test_create_ignores_role_fields(self) -> None:
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/leagues/",
            {
                "name": "Seeded League",
                "organization_id": self.org.pk,
                "admin_ids": [self.outsider.pk],
                "staff_ids": [self.outsider.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        league = League.objects.get(name="Seeded League")
        self.assertFalse(league.admins.exists())
        self.assertFalse(league.staff.exists())
