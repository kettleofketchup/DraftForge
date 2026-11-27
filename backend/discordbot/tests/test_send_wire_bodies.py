from typing import Any
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from discordbot import utils

API = "https://discord.com/api/v10"

EMBED_A: dict[str, Any] = {"title": "A", "description": "first", "color": 1}
EMBED_B: dict[str, Any] = {"title": "B", "fields": [{"name": "n", "value": "v"}]}
ROW: list[dict[str, Any]] = [
    {
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "Sign up", "custom_id": "event_signup:5"}
        ],
    }
]


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> MagicMock:
        self.calls.append((method, url, kwargs.get("json")))
        resp = MagicMock(status_code=200)
        if url.endswith("/users/@me/channels"):
            resp.json.return_value = {"id": "dm-chan"}
        else:
            resp.json.return_value = {"id": "m1"}
        return resp


class ChannelSendWireBodyTest(SimpleTestCase):
    def _send(self, **kwargs: Any) -> tuple[str, str, Any]:
        recorder = _Recorder()
        with patch("discordbot.utils._rate_limited_request", recorder):
            utils.sync_send_embed_with_components_no_log(channel_id="42", **kwargs)
        self.assertEqual(len(recorder.calls), 1)
        return recorder.calls[0]

    def test_single_embed_dict_wrapped_and_falsy_dropped(self) -> None:
        method, url, body = self._send(
            embed={"title": "A", "description": "first", "color": 1},
            components=[],
            content="",
            allowed_mentions=None,
        )
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"{API}/channels/42/messages")
        self.assertEqual(
            body, {"embeds": [{"title": "A", "description": "first", "color": 1}]}
        )

    def test_embed_list_used_as_is(self) -> None:
        _, url, body = self._send(embed=[EMBED_A, EMBED_B], components=ROW)
        self.assertEqual(url, f"{API}/channels/42/messages")
        self.assertEqual(
            body,
            {
                "embeds": [
                    {"title": "A", "description": "first", "color": 1},
                    {"title": "B", "fields": [{"name": "n", "value": "v"}]},
                ],
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 3,
                                "label": "Sign up",
                                "custom_id": "event_signup:5",
                            }
                        ],
                    }
                ],
            },
        )

    def test_empty_embed_list_with_content(self) -> None:
        _, url, body = self._send(
            embed=[],
            content="hi",
            allowed_mentions={"users": ["1"]},
            message_reference={"message_id": "9", "fail_if_not_exists": False},
        )
        self.assertEqual(url, f"{API}/channels/42/messages")
        self.assertEqual(
            body,
            {
                "embeds": [],
                "content": "hi",
                "allowed_mentions": {"users": ["1"]},
                "message_reference": {"message_id": "9", "fail_if_not_exists": False},
            },
        )

    def test_forum_thread_body_truncates_name_to_100(self) -> None:
        name = "x" * 150
        _, url, body = self._send(
            embed={"title": "A"}, components=ROW, forum_thread_name=name
        )
        self.assertEqual(url, f"{API}/channels/42/threads")
        self.assertEqual(
            body,
            {
                "name": "x" * 100,
                "message": {
                    "embeds": [{"title": "A"}],
                    "components": [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 3,
                                    "label": "Sign up",
                                    "custom_id": "event_signup:5",
                                }
                            ],
                        }
                    ],
                },
            },
        )

    def test_message_reference_and_allowed_mentions_kept(self) -> None:
        _, _, body = self._send(
            embed={"title": "A"},
            content="<@&7> starting",
            allowed_mentions={"roles": ["7"], "parse": []},
            message_reference={"message_id": "3", "fail_if_not_exists": False},
        )
        self.assertEqual(
            body,
            {
                "embeds": [{"title": "A"}],
                "content": "<@&7> starting",
                "allowed_mentions": {"roles": ["7"], "parse": []},
                "message_reference": {"message_id": "3", "fail_if_not_exists": False},
            },
        )

    def test_logged_send_posts_same_body(self) -> None:
        recorder = _Recorder()
        with (
            patch("discordbot.utils._rate_limited_request", recorder),
            patch("discordbot.utils._log_discord_message", return_value=1),
        ):
            utils.sync_send_embed_with_components(
                channel_id="42",
                embed=[EMBED_A],
                components=ROW,
                content="hello",
                source="test",
                source_id=None,
            )
        self.assertEqual(len(recorder.calls), 1)
        _, url, body = recorder.calls[0]
        self.assertEqual(url, f"{API}/channels/42/messages")
        self.assertEqual(
            body,
            {
                "embeds": [{"title": "A", "description": "first", "color": 1}],
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 3,
                                "label": "Sign up",
                                "custom_id": "event_signup:5",
                            }
                        ],
                    }
                ],
                "content": "hello",
            },
        )


@override_settings(TEST=False)
class DmSendWireBodyTest(SimpleTestCase):
    def _send_dm(self, **kwargs: Any) -> list[Any]:
        recorder = _Recorder()
        with patch("discordbot.utils._rate_limited_request", recorder):
            utils.sync_send_dm("555", **kwargs)
        self.assertEqual(
            recorder.calls[0],
            ("POST", f"{API}/users/@me/channels", {"recipient_id": "555"}),
        )
        message_posts = [
            body
            for method, url, body in recorder.calls
            if method == "POST" and url == f"{API}/channels/dm-chan/messages"
        ]
        self.assertEqual(len(message_posts), 1)
        return message_posts

    def test_dm_body_embed_dict_and_components(self) -> None:
        (body,) = self._send_dm(embed={"title": "A"}, components=ROW)
        self.assertEqual(
            body,
            {
                "embeds": [{"title": "A"}],
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 3,
                                "label": "Sign up",
                                "custom_id": "event_signup:5",
                            }
                        ],
                    }
                ],
            },
        )

    def test_dm_body_content_only_drops_empty_components(self) -> None:
        (body,) = self._send_dm(content="hello", embed=None, components=[])
        self.assertEqual(body, {"content": "hello"})
