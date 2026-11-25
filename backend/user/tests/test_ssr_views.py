from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser


class SSREndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_user_ssr_returns_200(self) -> None:
        user = CustomUser.objects.create_user(
            username="testplayer", password="testpass123"
        )
        resp = self.client.get(f"/api/users/{user.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "testplayer")
        self.assertIn("avatar_url", resp.data)
        self.assertNotIn("avatar", resp.data)
        self.assertNotIn("email", resp.data)
