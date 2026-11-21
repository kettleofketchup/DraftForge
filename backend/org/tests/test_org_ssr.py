"""Tests for the organization SSR meta tag endpoint."""

from django.test import TestCase
from rest_framework.test import APIClient

from org.models import Organization


class OrganizationSSREndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_organization_ssr_returns_200(self) -> None:
        org = Organization.objects.create(name="Test Org", description="A test org")
        resp = self.client.get(f"/api/organizations/{org.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test Org")
        self.assertEqual(resp.data["description"], "A test org")
        self.assertNotIn("admins", resp.data)
        self.assertNotIn("staff", resp.data)
