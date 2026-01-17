"""Tests for joke API endpoints."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, Joke


class JokeAPITest(TestCase):
    """Test joke API endpoints."""

    def setUp(self):
        """Create test user."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.client = APIClient()

    def test_get_tangoes_requires_auth(self):
        """GET /api/jokes/tangoes/ requires authentication."""
        response = self.client.get("/api/jokes/tangoes/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_tangoes_creates_joke_if_not_exists(self):
        """GET /api/jokes/tangoes/ creates Joke record if none exists."""
        self.client.force_authenticate(user=self.user)

        self.assertFalse(Joke.objects.filter(user=self.user).exists())

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 0)
        self.assertTrue(Joke.objects.filter(user=self.user).exists())

    def test_get_tangoes_returns_existing_count(self):
        """GET /api/jokes/tangoes/ returns existing tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=42)

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 42)

    def test_buy_tango_requires_auth(self):
        """POST /api/jokes/tangoes/buy/ requires authentication."""
        response = self.client.post("/api/jokes/tangoes/buy/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_buy_tango_increments_count(self):
        """POST /api/jokes/tangoes/buy/ increments tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=10)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 11)
        self.assertIn("message", response.data)

    def test_buy_tango_creates_joke_if_not_exists(self):
        """POST /api/jokes/tangoes/buy/ creates Joke if none exists."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 1)
