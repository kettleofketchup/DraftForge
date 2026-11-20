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


class ApiRootTests(TestCase):
    def test_api_root_lists_organizations(self) -> None:
        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("organizations", response.json())
