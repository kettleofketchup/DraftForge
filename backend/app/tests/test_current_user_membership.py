from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization
from org.membership import member_organization_ids
from org.models import OrgUser

CURRENT_USER_URL = "/api/current_user"
USERS_URL = "/api/users/"


@override_settings(CACHEOPS_ENABLED=False)
class MemberOrganizationIdsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(username="member", password="x")
        cls.other = CustomUser.objects.create_user(username="other", password="x")
        cls.orgs = {
            key: Organization.objects.create(name=f"Org {key}") for key in "ABCDEFG"
        }

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _ids(self) -> list[int]:
        response = self.client.get(CURRENT_USER_URL)
        self.assertEqual(response.status_code, 201)
        return response.json()["member_organization_ids"]

    def test_org_user_member(self) -> None:
        OrgUser.objects.create(user=self.user, organization=self.orgs["A"])
        self.assertEqual(self._ids(), [self.orgs["A"].pk])

    def test_org_admin_only(self) -> None:
        self.orgs["B"].admins.add(self.user)
        self.assertEqual(self._ids(), [self.orgs["B"].pk])

    def test_org_staff_only(self) -> None:
        self.orgs["C"].staff.add(self.user)
        self.assertEqual(self._ids(), [self.orgs["C"].pk])

    def test_org_owner(self) -> None:
        self.orgs["D"].owner = self.user
        self.orgs["D"].save()
        self.assertEqual(self._ids(), [self.orgs["D"].pk])

    def test_league_admin(self) -> None:
        league = League.objects.create(organization=self.orgs["E"], name="E League")
        league.admins.add(self.user)
        self.assertEqual(self._ids(), [self.orgs["E"].pk])

    def test_league_staff_only(self) -> None:
        league = League.objects.create(organization=self.orgs["F"], name="F League")
        league.staff.add(self.user)
        self.assertEqual(self._ids(), [self.orgs["F"].pk])

    def test_league_staff_without_organization(self) -> None:
        league = League.objects.create(organization=None, name="Orphan League")
        league.staff.add(self.user)
        self.assertEqual(self._ids(), [])

    def test_member_and_admin_of_same_org_is_distinct(self) -> None:
        OrgUser.objects.create(user=self.user, organization=self.orgs["A"])
        self.orgs["A"].admins.add(self.user)
        self.assertEqual(self._ids(), [self.orgs["A"].pk])

    def test_no_orgs(self) -> None:
        OrgUser.objects.create(user=self.other, organization=self.orgs["A"])
        self.assertEqual(self._ids(), [])

    def test_values_sorted(self) -> None:
        OrgUser.objects.create(user=self.user, organization=self.orgs["G"])
        self.orgs["C"].staff.add(self.user)
        self.orgs["A"].admins.add(self.user)
        league = League.objects.create(organization=self.orgs["E"], name="E League")
        league.admins.add(self.user)
        expected = sorted(self.orgs[k].pk for k in "ACEG")
        self.assertEqual(self._ids(), expected)

    def test_anonymous_returns_empty_200(self) -> None:
        response = APIClient().get(CURRENT_USER_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_helper_queries(self) -> None:
        with self.assertNumQueries(2):
            member_organization_ids(self.user, admin_org_ids=[], staff_org_ids=[])

    def test_helper_merges_passed_ids(self) -> None:
        result = member_organization_ids(
            self.user,
            admin_org_ids=[self.orgs["D"].pk, self.orgs["B"].pk],
            staff_org_ids=[self.orgs["B"].pk],
        )
        self.assertEqual(result, sorted([self.orgs["B"].pk, self.orgs["D"].pk]))

    def test_current_user_adds_at_most_two_queries(self) -> None:
        with mock.patch("app.views_main.member_organization_ids", return_value=[]):
            with CaptureQueriesContext(connection) as patched:
                self.client.get(CURRENT_USER_URL)
        with CaptureQueriesContext(connection) as unpatched:
            self.client.get(CURRENT_USER_URL)
        self.assertLessEqual(len(unpatched) - len(patched), 2)

    def test_users_list_unchanged(self) -> None:
        response = self.client.get(USERS_URL)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("member_organization_ids", row)
