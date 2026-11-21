from django.test import SimpleTestCase, TestCase
from django.urls import resolve

from org import ssr, views_organization


class OrgRouteResolutionTests(SimpleTestCase):
    def test_organization_viewset_lives_in_org(self) -> None:
        cases = {
            "/api/organizations/": "organization-list",
            "/api/organizations/1/": "organization-detail",
            "/api/organizations/1/users/": "organization-users",
        }
        for path, url_name in cases.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertIs(match.func.cls, views_organization.OrganizationView)
                self.assertEqual(match.url_name, url_name)

    def test_org_ssr_view_lives_in_org(self) -> None:
        match = resolve("/api/organizations/1/ssr/")
        self.assertIs(match.func.view_class, ssr.OrganizationSSRView)
        self.assertEqual(match.url_name, "organization_ssr")

    def test_org_admin_team_routes_live_in_org(self) -> None:
        cases = {
            "/api/organizations/1/admins/": "add_org_admin",
            "/api/organizations/1/admins/2/": "remove_org_admin",
            "/api/organizations/1/staff/": "add_org_staff",
            "/api/organizations/1/staff/2/": "remove_org_staff",
            "/api/organizations/1/transfer-ownership/": "transfer_org_ownership",
            "/api/organizations/1/members/": "add_org_member",
            "/api/organizations/1/users/2/": "update_org_user",
        }
        for path, url_name in cases.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.func.__module__, "org.views_admin_team")
                self.assertEqual(match.func.cls.__name__, url_name)
                self.assertEqual(match.url_name, url_name)


class ApiRootTests(TestCase):
    def test_api_root_lists_organizations(self) -> None:
        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("organizations", response.json())
