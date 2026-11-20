from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from app.models import CustomUser

REFRESH_URL = "/api/avatars/refresh/"
RATE_LIMIT_KEY = "avatar_refresh_last_run"
RATE_LIMIT_MESSAGE = "Avatar refresh can only be run once per hour."
DELAY_TARGET = "app.tasks.avatar_refresh.refresh_avatars_batched.delay"
LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


@override_settings(CACHES=LOCMEM_CACHE)
class RefreshAllAvatarsRateLimitTest(TestCase):
    def setUp(self) -> None:
        cache.delete(RATE_LIMIT_KEY)
        self.addCleanup(cache.delete, RATE_LIMIT_KEY)
        self.client = APIClient()

    @patch(DELAY_TARGET)
    def test_anonymous_post_queues_refresh(self, delay: MagicMock) -> None:
        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with()
        self.assertIsNotNone(cache.get(RATE_LIMIT_KEY))

    @patch(DELAY_TARGET)
    def test_repeated_calls_queue_only_once(self, delay: MagicMock) -> None:
        responses = [self.client.post(REFRESH_URL) for _ in range(5)]

        self.assertEqual(responses[0].status_code, 202)
        for response in responses[1:]:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["message"], RATE_LIMIT_MESSAGE)
        delay.assert_called_once_with()

    @patch(DELAY_TARGET)
    def test_limit_is_shared_across_callers(self, delay: MagicMock) -> None:
        anonymous = self.client.post(REFRESH_URL)

        user = CustomUser.objects.create(username="avatar_plain_user")
        self.client.force_authenticate(user=user)
        plain = self.client.post(REFRESH_URL)

        staff = CustomUser.objects.create(username="avatar_staff", is_staff=True)
        self.client.force_authenticate(user=staff)
        staff_response = self.client.post(REFRESH_URL)

        self.assertEqual(anonymous.status_code, 202)
        self.assertEqual(plain.status_code, 200)
        self.assertEqual(staff_response.status_code, 200)
        delay.assert_called_once_with()

    @patch(DELAY_TARGET)
    def test_refresh_runs_again_after_limit_expires(self, delay: MagicMock) -> None:
        self.client.post(REFRESH_URL)
        cache.delete(RATE_LIMIT_KEY)

        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(delay.call_count, 2)

    @patch(DELAY_TARGET)
    def test_get_is_not_allowed(self, delay: MagicMock) -> None:
        response = self.client.get(REFRESH_URL)

        self.assertEqual(response.status_code, 405)
        delay.assert_not_called()


class AjaxAuthRemovedTest(TestCase):
    def test_route_is_not_reversible(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("ajax-auth", kwargs={"backend": "discord"})

    def test_route_returns_404(self) -> None:
        response = self.client.get("/ajax-auth/discord/")

        self.assertEqual(response.status_code, 404)
