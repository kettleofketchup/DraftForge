"""Access control for org member lists."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, League
from org.models import Organization, OrgUser
from org.permissions import (
    can_view_org_members,
    can_view_org_members_from_payload,
)
from tests.populate.utils import ensure_org_user


class OrgMembersPrivacyTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.admin = CustomUser.objects.create_user(username="admin", password="x")
        self.staff = CustomUser.objects.create_user(username="staff", password="x")
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )
        self.site_admin = CustomUser.objects.create_superuser(
            username="site", password="x"
        )

        self.org = Organization.objects.create(name="Privacy Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        ensure_org_user(self.member, self.org, mmr=4200)

        self.client = APIClient()
        self.url = f"/api/organizations/{self.org.pk}/users/"

    def _status_for(self, user: CustomUser | None) -> int:
        self.client.force_authenticate(user=user)
        return self.client.get(self.url).status_code

    def _set_private(self, private: bool) -> None:
        self.org.members_private = private
        self.org.save()

    def test_default_allows_members_and_staff(self) -> None:
        for user in (self.member, self.staff, self.admin, self.owner, self.site_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)

    def test_default_denies_outsiders(self) -> None:
        self.assertEqual(self._status_for(None), status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._status_for(self.outsider), status.HTTP_403_FORBIDDEN)

    def test_private_allows_only_staff_tier(self) -> None:
        self._set_private(True)
        for user in (self.staff, self.admin, self.owner, self.site_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)
        for user in (self.member, self.outsider, None):
            with self.subTest(user=getattr(user, "username", "anon")):
                self.assertEqual(self._status_for(user), status.HTTP_403_FORBIDDEN)

    def test_member_cache_not_served_to_outsider(self) -> None:
        self.assertEqual(self._status_for(self.member), status.HTTP_200_OK)
        self.assertEqual(self._status_for(self.outsider), status.HTTP_403_FORBIDDEN)

    def test_private_toggle_takes_effect_after_cached_read(self) -> None:
        self.assertEqual(self._status_for(self.member), status.HTTP_200_OK)
        self._set_private(True)
        self.assertEqual(self._status_for(self.member), status.HTTP_403_FORBIDDEN)

    def test_retrieve_reports_viewer_access(self) -> None:
        detail = f"/api/organizations/{self.org.pk}/"
        cases = [(self.member, True), (self.outsider, False), (None, False)]
        for user, expected in cases:
            with self.subTest(user=getattr(user, "username", "anon")):
                self.client.force_authenticate(user=user)
                data = self.client.get(detail).data
                self.assertIs(data["can_view_members"], expected)
                self.assertIs(data["members_private"], False)
                self.assertEqual(data["members_viewer_pk"], getattr(user, "pk", None))

    def test_retrieve_access_flag_respects_private(self) -> None:
        self._set_private(True)
        detail = f"/api/organizations/{self.org.pk}/"
        for user, expected in [(self.member, False), (self.staff, True)]:
            with self.subTest(user=user.username):
                self.client.force_authenticate(user=user)
                self.assertIs(
                    self.client.get(detail).data["can_view_members"], expected
                )

    def test_admin_can_toggle_private_staff_cannot(self) -> None:
        detail = f"/api/organizations/{self.org.pk}/"
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(detail, {"members_private": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(detail, {"members_private": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertTrue(self.org.members_private)

    def test_patch_response_reports_viewer_access(self) -> None:
        self.client.force_authenticate(user=self.admin)
        detail = f"/api/organizations/{self.org.pk}/"
        resp = self.client.patch(detail, {"members_private": True}, format="json")
        self.assertIs(resp.data["can_view_members"], True)
        self.assertEqual(resp.data["members_viewer_pk"], self.admin.pk)

    def test_league_staff_without_org_membership_can_view(self) -> None:
        league_admin = CustomUser.objects.create_user(username="ladmin", password="x")
        league_staff = CustomUser.objects.create_user(username="lstaff", password="x")
        league = League.objects.create(
            name="Org League", organization=self.org, steam_league_id=515151
        )
        league.admins.add(league_admin)
        league.staff.add(league_staff)
        self._set_private(True)
        detail = f"/api/organizations/{self.org.pk}/"
        for user in (league_admin, league_staff):
            with self.subTest(user=user.username):
                self.assertFalse(
                    OrgUser.objects.filter(user=user, organization=self.org).exists()
                )
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)
                self.assertIs(self.client.get(detail).data["can_view_members"], True)

    def test_staff_of_another_orgs_league_cannot_view(self) -> None:
        other_org = Organization.objects.create(name="Other Org", owner=self.owner)
        league = League.objects.create(
            name="Other League", organization=other_org, steam_league_id=525252
        )
        league.staff.add(self.outsider)
        self.assertEqual(self._status_for(self.outsider), status.HTTP_403_FORBIDDEN)

    def test_permission_check_is_a_single_query(self) -> None:
        with self.assertNumQueries(1):
            self.assertTrue(can_view_org_members(self.member, self.org.pk))
        with self.assertNumQueries(1):
            self.assertFalse(can_view_org_members(self.outsider, self.org))

    def test_payload_check_skips_query_for_listed_staff(self) -> None:
        payload = {
            "pk": self.org.pk,
            "owner": {"pk": self.owner.pk},
            "admins": [{"pk": self.admin.pk}],
            "staff": [{"pk": self.staff.pk}],
        }
        with self.assertNumQueries(0):
            for user in (self.owner, self.admin, self.staff, self.site_admin):
                self.assertTrue(can_view_org_members_from_payload(user, payload))
