"""Tests for League API endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization


class LeagueAPITest(TestCase):
    """Test league API endpoints."""

    def setUp(self):
        """Create test data."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.org_admin = CustomUser.objects.create_user(
            username="orgadmin",
            password="test123",
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin",
            password="test123",
        )
        self.org = Organization.objects.create(name="Test Org")
        self.org.admins.add(self.org_admin)
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name="Test League",
        )
        self.league.admins.add(self.league_admin)
        self.client = APIClient()

    def test_list_leagues_public(self):
        """GET /api/leagues/ is public."""
        response = self.client.get("/api/leagues/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_leagues_by_org(self):
        """GET /api/leagues/?organization={id} filters correctly."""
        other_org = Organization.objects.create(name="Other Org")
        League.objects.create(
            organization=other_org,
            steam_league_id=99999,
            name="Other League",
        )
        response = self.client.get(f"/api/leagues/?organization={self.org.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Test League")

    def test_create_league_requires_org_admin(self):
        """POST /api/leagues/ requires org admin."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/leagues/",
            {
                "organization": self.org.pk,
                "steam_league_id": 54321,
                "name": "New League",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(
            "/api/leagues/",
            {
                "organization": self.org.pk,
                "steam_league_id": 54321,
                "name": "New League",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_league_org_admin_access(self):
        """PATCH allows org admin to update league."""
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Updated by Org Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_league_league_admin_access(self):
        """PATCH allows league admin to update league."""
        self.client.force_authenticate(user=self.league_admin)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Updated by League Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_league_denied_regular_user(self):
        """PATCH denied for regular users."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/leagues/{self.league.pk}/",
            {"name": "Should Fail"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_org_admin_inherits_league_access(self):
        """Org admin can update any league in their org."""
        new_league = League.objects.create(
            organization=self.org,
            steam_league_id=11111,
            name="Another League",
        )
        # new_league has no admins, but org_admin should still have access
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.patch(
            f"/api/leagues/{new_league.pk}/",
            {"name": "Updated via Org Admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
