from typing import Any
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization

GUILD = "424242"
URL_TEMPLATE = "/api/discord/organizations/{pk}/channels/"

RAW_CHANNELS: list[dict[str, Any]] = [
    {"id": "1", "name": "general", "type": 0},
    {"id": "2", "name": "Lobby Voice", "type": 2},
    {"id": "3", "name": "news", "type": 5},
    {"id": "4", "name": "Main Stage", "type": 13},
    {"id": "5", "name": "lfg-forum", "type": 15},
    {"id": "6", "name": "Category", "type": 4},
]


def _resp() -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = RAW_CHANNELS
    resp.raise_for_status.return_value = None
    return resp


@override_settings(
    DISCORD_BOT_TOKEN="t",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test_channels_kind",
        }
    },
)
class ChannelKindTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = CustomUser.objects.create_user(
            username="channels_staff", password="x"
        )
        cls.outsider = CustomUser.objects.create_user(
            username="channels_outsider", password="x"
        )
        cls.org = Organization.objects.create(
            name="Channels Org", owner=cls.staff, discord_server_id=GUILD
        )
        cls.org.staff.add(cls.staff)

    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.url = URL_TEMPLATE.format(pk=self.org.pk)

    def _get(self, **params: str) -> Any:
        return self.client.get(self.url, params)

    @patch("discordbot.services.channels.requests.get")
    def test_voice_kind_lists_voice_and_stage(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resp()
        res = self._get(kind="voice")
        self.assertEqual(res.status_code, 200)
        channels = res.json()["channels"]
        self.assertEqual({c["type"] for c in channels}, {2, 13})
        self.assertEqual(
            {c["type"]: c["type_label"] for c in channels}, {2: "voice", 13: "stage"}
        )

    @patch("discordbot.services.channels.requests.get")
    def test_text_kind_unchanged(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resp()
        res = self._get()
        self.assertEqual(res.status_code, 200)
        channels = res.json()["channels"]
        self.assertEqual({c["type"] for c in channels}, {0, 5, 15})
        self.assertEqual(
            {c["type"]: c["type_label"] for c in channels},
            {0: "text", 5: "announcement", 15: "forum"},
        )
        self.assertIsNotNone(cache.get(f"discord_channels_{GUILD}"))

    @patch("discordbot.services.channels.requests.get")
    def test_kinds_cached_separately(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resp()
        text = self._get(kind="text").json()["channels"]
        voice = self._get(kind="voice").json()["channels"]
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(self._get(kind="text").json()["channels"], text)
        self.assertEqual(self._get(kind="voice").json()["channels"], voice)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual({c["type"] for c in voice}, {2, 13})
        self.assertEqual(
            {c["type"] for c in cache.get(f"discord_channels_voice_{GUILD}")},
            {2, 13},
        )

    @patch("discordbot.services.channels.requests.get")
    def test_refresh_clears_both_kinds(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resp()
        self._get(kind="text")
        self._get(kind="voice")
        self.assertEqual(mock_get.call_count, 2)

        self._get(kind="text", refresh="true")
        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNone(cache.get(f"discord_channels_voice_{GUILD}"))

        self._get(kind="voice")
        self.assertEqual(mock_get.call_count, 4)

    @patch("discordbot.services.channels.requests.get")
    def test_unknown_kind_400(self, mock_get: MagicMock) -> None:
        res = self._get(kind="category")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {"error": "Unknown channel kind"})
        mock_get.assert_not_called()

    @patch("discordbot.services.channels.requests.get")
    def test_non_staff_403(self, mock_get: MagicMock) -> None:
        self.client.force_authenticate(self.outsider)
        res = self._get(kind="voice")
        self.assertEqual(res.status_code, 403)
        mock_get.assert_not_called()
