from django.apps import apps
from django.test import SimpleTestCase
from django.urls import resolve


class UserAppRegistrationTests(SimpleTestCase):
    def test_app_is_installed(self):
        assert apps.is_installed("user")

    def test_app_config_name(self):
        config = apps.get_app_config("user")
        assert config.name == "user"

    def test_placeholder_url_resolves(self):
        match = resolve("/api/users/me/profile/")
        assert match.url_name == "me-profile"
