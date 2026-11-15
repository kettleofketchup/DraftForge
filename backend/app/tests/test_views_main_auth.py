from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from app.models import CustomUser

REFRESH_URL = "/api/avatars/refresh/"
RATE_LIMIT_KEY = "avatar_refresh_last_run"
DELAY_TARGET = "app.tasks.avatar_refresh.refresh_avatars_batched.delay"


class RefreshAllAvatarsPermissionTest(TestCase):
    def setUp(self) -> None:
        cache.delete(RATE_LIMIT_KEY)
        self.addCleanup(cache.delete, RATE_LIMIT_KEY)
        self.client = APIClient()

    @patch(DELAY_TARGET)
    def test_anonymous_post_is_rejected(self, delay: MagicMock) -> None:
        response = self.client.post(REFRESH_URL)

        self.assertIn(response.status_code, (401, 403))
        delay.assert_not_called()
        self.assertIsNone(cache.get(RATE_LIMIT_KEY))

    @patch(DELAY_TARGET)
    def test_anonymous_get_is_rejected(self, delay: MagicMock) -> None:
        response = self.client.get(REFRESH_URL)

        self.assertIn(response.status_code, (401, 403))
        delay.assert_not_called()

    @patch(DELAY_TARGET)
    def test_plain_user_is_forbidden(self, delay: MagicMock) -> None:
        user = CustomUser.objects.create(username="avatar_plain_user")
        self.client.force_authenticate(user=user)

        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, 403)
        delay.assert_not_called()
        self.assertIsNone(cache.get(RATE_LIMIT_KEY))

    @patch(DELAY_TARGET)
    def test_staff_queues_refresh_once_per_hour(self, delay: MagicMock) -> None:
        staff = CustomUser.objects.create(username="avatar_staff", is_staff=True)
        self.client.force_authenticate(user=staff)

        first = self.client.post(REFRESH_URL)
        second = self.client.post(REFRESH_URL)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            second.data["message"], "Avatar refresh can only be run once per hour."
        )
        delay.assert_called_once_with()


class AjaxAuthRemovedTest(TestCase):
    def test_route_is_not_reversible(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("ajax-auth", kwargs={"backend": "discord"})

    def test_route_returns_404(self) -> None:
        response = self.client.get("/ajax-auth/discord/")

        self.assertEqual(response.status_code, 404)
