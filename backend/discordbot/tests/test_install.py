from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.install_schemas import DiscordBotStatus, DiscordInstallLink
from discordbot.services.install import STATE_SALT
from discordbot.services.users import bot_access_cache_key
from org.models import Organization

GUILD = "123456789012345678"
OTHER_GUILD = "876543210987654321"
APP = {
    "id": "999000111222333444",
    "install_params": {
        "scopes": ["bot", "applications.commands"],
        "permissions": "68672",
    },
}
CALLBACK = "/api/discord/install/callback/"


def _resp(status: int, body: Any = None) -> MagicMock:
    resp = MagicMock(status_code=status)
    resp.json.return_value = body
    return resp


def _discord(app_status: int = 200, guild_status: int = 200) -> Any:
    def fake_get(url: str, **_: Any) -> MagicMock:
        if url.endswith("/applications/@me"):
            return _resp(app_status, APP)
        if "/members" in url:
            return _resp(guild_status, [])
        return _resp(guild_status, {"id": GUILD, "name": "Kettle Server"})

    return patch("requests.get", side_effect=fake_get)


@override_settings(
    DISCORD_BOT_TOKEN="t",
    SITE_URL="https://draftforge.test",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test_discord_install",
        }
    },
)
class DiscordInstallTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CustomUser.objects.create_user(
            username="install_owner", password="x"
        )
        cls.admin = CustomUser.objects.create_user(
            username="install_admin", password="x"
        )
        cls.staff = CustomUser.objects.create_user(
            username="install_staff", password="x"
        )
        cls.org = Organization.objects.create(name="Install Org", owner=cls.owner)
        cls.org.admins.add(cls.admin)
        cls.org.staff.add(cls.staff)

    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()

    def _link(self, user: CustomUser) -> Any:
        self.client.force_authenticate(user)
        return self.client.get(
            f"/api/discord/organizations/{self.org.pk}/install-link/"
        )

    def _state(self, user: CustomUser) -> str:
        return signing.dumps({"org": self.org.pk, "user": user.pk}, salt=STATE_SALT)

    def _callback(self, user: CustomUser | None, **params: str) -> Any:
        if user is not None:
            self.client.force_login(user)
        return self.client.get(CALLBACK, params)

    def _query(self, response: Any) -> dict[str, list[str]]:
        location = urlparse(response["Location"])
        return {"path": [location.path], **parse_qs(location.query)}

    def test_link_for_admin_carries_install_params_and_state(self) -> None:
        with _discord():
            response = self._link(self.admin)

        self.assertEqual(response.status_code, 200)
        url = urlparse(DiscordInstallLink.model_validate(response.json()).url)
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], [APP["id"]])
        self.assertEqual(query["scope"], ["bot applications.commands"])
        self.assertEqual(query["permissions"], ["68672"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(
            query["redirect_uri"],
            ["https://draftforge.test/api/discord/install/callback/"],
        )
        self.assertNotIn("guild_id", query)
        state = signing.loads(query["state"][0], salt=STATE_SALT)
        self.assertEqual(state, {"org": self.org.pk, "user": self.admin.pk})

    def test_link_preselects_configured_server(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(discord_server_id=GUILD)
        with _discord():
            response = self._link(self.owner)
        query = parse_qs(urlparse(response.json()["url"]).query)
        self.assertEqual(query["guild_id"], [GUILD])

    def test_link_forbidden_for_staff(self) -> None:
        with _discord():
            response = self._link(self.staff)
        self.assertEqual(response.status_code, 403)

    def test_link_unavailable_when_discord_fails(self) -> None:
        with _discord(app_status=500):
            response = self._link(self.admin)
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())

    def test_callback_saves_server_and_clears_stale_access_cache(self) -> None:
        cache.set(bot_access_cache_key(GUILD), False)
        with _discord():
            response = self._callback(
                self.admin, state=self._state(self.admin), guild_id=GUILD, code="c"
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self._query(response),
            {
                "path": [f"/organizations/{self.org.pk}"],
                "settings": ["discord"],
                "discord": ["connected"],
            },
        )
        self.org.refresh_from_db()
        self.assertEqual(self.org.discord_server_id, GUILD)
        self.assertIsNone(cache.get(bot_access_cache_key(GUILD)))

    def _assert_error(self, response: Any, reason: str) -> None:
        self.assertEqual(response.status_code, 302)
        query = self._query(response)
        self.assertEqual(query["discord"], ["error"])
        self.assertEqual(query["reason"], [reason])
        self.org.refresh_from_db()
        self.assertIsNone(self.org.discord_server_id)

    def test_callback_cancelled(self) -> None:
        response = self._callback(
            self.admin, state=self._state(self.admin), error="access_denied"
        )
        self._assert_error(response, "cancelled")

    def test_callback_bad_state(self) -> None:
        response = self._callback(self.admin, state="tampered", guild_id=GUILD)
        self._assert_error(response, "expired")
        self.assertEqual(self._query(response)["path"], ["/organizations"])

    def test_callback_expired_state(self) -> None:
        state = self._state(self.admin)
        with patch("discordbot.services.install.STATE_MAX_AGE_S", -1):
            response = self._callback(self.admin, state=state, guild_id=GUILD)
        self._assert_error(response, "expired")

    def test_callback_rejects_different_user(self) -> None:
        response = self._callback(
            self.owner, state=self._state(self.admin), guild_id=GUILD
        )
        self._assert_error(response, "forbidden")

    def test_callback_rejects_signed_out(self) -> None:
        response = self._callback(None, state=self._state(self.admin), guild_id=GUILD)
        self._assert_error(response, "forbidden")

    def test_callback_rejects_demoted_admin(self) -> None:
        state = self._state(self.admin)
        self.org.admins.remove(self.admin)
        response = self._callback(self.admin, state=state, guild_id=GUILD)
        self._assert_error(response, "forbidden")

    def test_callback_rejects_malformed_guild(self) -> None:
        response = self._callback(
            self.admin, state=self._state(self.admin), guild_id="../../x"
        )
        self._assert_error(response, "invalid_server")

    def test_callback_rejects_guild_bot_cannot_see(self) -> None:
        with _discord(guild_status=403):
            response = self._callback(
                self.admin, state=self._state(self.admin), guild_id=OTHER_GUILD
            )
        self._assert_error(response, "bot_missing")

    def test_bot_status_denies_unrelated_user(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(discord_server_id=GUILD)
        unrelated = CustomUser.objects.create_user(username="unrelated_status")
        self.client.force_authenticate(unrelated)
        with patch("discordbot.services.install.check_bot_guild_access") as access:
            response = self.client.get(
                f"/api/discord/organizations/{self.org.pk}/bot-status/"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Permission denied"})
        access.assert_not_called()

    def test_bot_status_allows_org_staff(self) -> None:
        self.client.force_authenticate(self.staff)
        response = self.client.get(
            f"/api/discord/organizations/{self.org.pk}/bot-status/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "no_server_configured")

    def test_status_without_server(self) -> None:
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f"/api/discord/organizations/{self.org.pk}/bot-status/"
        )
        status = DiscordBotStatus.model_validate(response.json())
        self.assertEqual(
            status,
            DiscordBotStatus(
                has_bot=False, reason="no_server_configured", guild_name=None
            ),
        )

    def test_status_includes_guild_name(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(discord_server_id=GUILD)
        self.client.force_authenticate(self.admin)
        with _discord():
            response = self.client.get(
                f"/api/discord/organizations/{self.org.pk}/bot-status/"
            )
        self.assertEqual(
            response.json(),
            {"has_bot": True, "reason": None, "guild_name": "Kettle Server"},
        )

    def test_status_without_bot_omits_name(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(discord_server_id=GUILD)
        self.client.force_authenticate(self.admin)
        with _discord(guild_status=403):
            response = self.client.get(
                f"/api/discord/organizations/{self.org.pk}/bot-status/"
            )
        self.assertEqual(
            response.json(), {"has_bot": False, "reason": None, "guild_name": None}
        )
