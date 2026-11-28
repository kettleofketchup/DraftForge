from urllib.parse import parse_qs, urlparse

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from social_core.backends.discord import DiscordOAuth2
from social_django.utils import load_strategy


@override_settings(SOCIAL_AUTH_DISCORD_KEY="123456789012345678")
class DiscordOAuthScopeTest(SimpleTestCase):
    def _backend(self) -> DiscordOAuth2:
        request = RequestFactory().get("/api/login/discord/")
        request.session = {}
        return DiscordOAuth2(load_strategy(request), redirect_uri="/complete/")

    def test_scope_requests_only_identify(self) -> None:
        self.assertEqual(self._backend().get_scope(), ["identify"])

    def test_authorization_url_requests_only_identify(self) -> None:
        url = self._backend().auth_url()
        scope = parse_qs(urlparse(url).query)["scope"][0]
        self.assertEqual(scope.split(" "), ["identify"])

    def test_user_guilds_endpoint_is_not_routed(self) -> None:
        with self.assertRaises(Resolver404):
            resolve("/api/discord/user-guilds/")
        with self.assertRaises(NoReverseMatch):
            reverse("discord-user-guilds")
