"""Tests for Organization API endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, Organization


class OrganizationAPITest(TestCase):
    """Test organization API endpoints."""

    def setUp(self):
        """Create test users and organization."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.org_admin = CustomUser.objects.create_user(
            username="orgadmin",
            password="test123",
        )
        self.superuser = CustomUser.objects.create_superuser(
            username="superuser",
            password="test123",
        )
        self.org = Organization.objects.create(
            name="Test Org",
            description="Test Description",
        )
        self.org.admins.add(self.org_admin)
        self.client = APIClient()

    def test_list_organizations_public(self):
        """GET /api/organizations/ is public."""
        response = self.client.get("/api/organizations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_organization_public(self):
        """GET /api/organizations/{id}/ is public."""
        response = self.client.get(f"/api/organizations/{self.org.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Org")

    def test_create_organization_requires_superuser(self):
        """POST /api/organizations/ requires superuser."""
        # Org admin (not superuser) should be denied
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/organizations/",
            {"name": "New Org"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Superuser should succeed
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {"name": "New Org"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_organization_requires_org_admin(self):
        """PATCH /api/organizations/{id}/ requires org admin."""
        # Regular user denied
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/",
            {"name": "Updated Name"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Org admin allowed
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/",
            {"name": "Updated Name"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_markdown_sanitization_script(self):
        """Organization sanitizes script tags."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test",
                "description": "<script>alert('xss')</script>Safe text",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("<script>", response.data["description"])
        self.assertIn("Safe text", response.data["description"])

    def test_markdown_sanitization_event_handlers(self):
        """Organization sanitizes event handlers."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test 2",
                "description": '<img src="x" onerror="alert(1)">Safe',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("onerror", response.data["description"])

    def test_markdown_sanitization_javascript_url(self):
        """Organization sanitizes javascript: URLs."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            "/api/organizations/",
            {
                "name": "XSS Test 3",
                "description": '<a href="javascript:alert(1)">Click</a>',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("javascript:", response.data["description"])
