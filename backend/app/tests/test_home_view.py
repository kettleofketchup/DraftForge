"""Tests for the server-rendered `home` view mounted at `/` and `/login/`."""

from django.test import TestCase, override_settings

from app.models import CustomUser

SITE_URL = "https://site.example"


@override_settings(SITE_URL=SITE_URL)
class HomeViewTest(TestCase):
    def test_anonymous_login_page_renders(self) -> None:
        resp = self.client.get("/login/")
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_login_redirects_to_frontend_root(self) -> None:
        user = CustomUser.objects.create(username="home_view_user")
        self.client.force_login(user)

        for path in ("/", "/login/"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, f"{SITE_URL}/", fetch_redirect_response=False
                )
