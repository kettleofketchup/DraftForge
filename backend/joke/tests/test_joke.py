"""Tests for joke API endpoints."""

from datetime import timedelta
from unittest.mock import patch

from django.db.models import F
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser
from joke.models import Joke


class JokeAPITest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create_user(
            username="testuser",
            password="test123",
        )
        self.client = APIClient()

    def test_get_tangoes_requires_auth(self) -> None:
        response = self.client.get("/api/jokes/tangoes/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_tangoes_creates_joke_if_not_exists(self) -> None:
        self.client.force_authenticate(user=self.user)

        self.assertFalse(Joke.objects.filter(user=self.user).exists())

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 0)
        self.assertTrue(Joke.objects.filter(user=self.user).exists())

    def test_get_tangoes_returns_existing_count(self) -> None:
        self.client.force_authenticate(user=self.user)
        Joke.objects.create(user=self.user, tangoes_purchased=42)

        response = self.client.get("/api/jokes/tangoes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 42)

    def test_buy_tango_requires_auth(self) -> None:
        response = self.client.post("/api/jokes/tangoes/buy/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_buy_tango_increments_count(self) -> None:
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

    def test_buy_tango_updates_timestamp(self) -> None:
        self.client.force_authenticate(user=self.user)
        joke = Joke.objects.create(user=self.user)
        previous = timezone.now() - timedelta(days=1)
        Joke.objects.filter(pk=joke.pk).update(updated_at=previous)
        before_purchase = timezone.now()

        response = self.client.post("/api/jokes/tangoes/buy/")

        joke.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(joke.updated_at, before_purchase)

    def test_buy_tango_creates_joke_if_not_exists(self) -> None:
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/jokes/tangoes/buy/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tangoes_purchased"], 1)
