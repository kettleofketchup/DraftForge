"""Tests for joke API endpoints."""

from unittest.mock import patch

from django.db.models import F
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser
from joke.models import Joke


class JokeAPITest(TestCase):
    """Test joke API endpoints."""

    def setUp(self) -> None:
        """Create test user."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.client = APIClient()

    def test_get_tangoes_requires_auth(self) -> None:
        """GET /api/jokes/tangoes/ requires authentication."""
        response = self.client.get("/api/jokes/tangoes/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_tangoes_creates_joke_if_not_exists(self) -> None:
        """GET /api/jokes/tangoes/ creates Joke record if none exists."""
        self.client.force_authenticate(user=self.user)

        self.assertFalse(Joke.objects.filter(user=self.user).exists())

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 0)
        self.assertTrue(Joke.objects.filter(user=self.user).exists())

    def test_get_tangoes_returns_existing_count(self) -> None:
        """GET /api/jokes/tangoes/ returns existing tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=42)

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 42)

    def test_buy_tango_requires_auth(self) -> None:
        """POST /api/jokes/tangoes/buy/ requires authentication."""
        response = self.client.post("/api/jokes/tangoes/buy/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_buy_tango_increments_count(self) -> None:
        """POST /api/jokes/tangoes/buy/ increments tango count."""
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=10)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 11)
        self.assertIn("message", response.data)

    def test_buy_tango_preserves_a_concurrent_increment(self) -> None:
        self.client.force_authenticate(user=self.user)
        stale_joke = Joke.objects.create(user=self.user, tangoes_purchased=10)
        Joke.objects.filter(pk=stale_joke.pk).update(
            tangoes_purchased=F("tangoes_purchased") + 1
        )

        with patch.object(
            Joke.objects, "get_or_create", return_value=(stale_joke, False)
        ):
            response = self.client.post("/api/jokes/tangoes/buy/")

        stale_joke.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(stale_joke.tangoes_purchased, 12)
        self.assertEqual(response.data["tangoes_purchased"], 12)

    def test_buy_tango_creates_joke_if_not_exists(self) -> None:
        """POST /api/jokes/tangoes/buy/ creates Joke if none exists."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 1)
