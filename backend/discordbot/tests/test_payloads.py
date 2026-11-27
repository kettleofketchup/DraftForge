import subprocess
import sys
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase
from pydantic import ValidationError

from discordbot.payload_schema import (
    ActionRow,
    Button,
    Container,
    DiscordMessage,
    Section,
    SelectMenu,
    TextDisplay,
    Thumbnail,
)
from discordbot.payloads import build_channel_message_payload, build_dm_payload

BACKEND = str(Path(__file__).resolve().parents[2])

ROW: list[dict[str, Any]] = [
    {
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "Sign up", "custom_id": "event_signup:5"}
        ],
    }
]


class BuildChannelMessagePayloadTest(SimpleTestCase):
    def test_single_embed_dict_wrapped_and_falsy_dropped(self) -> None:
        self.assertEqual(
            build_channel_message_payload(
                {"title": "A"}, components=[], content="", allowed_mentions=None
            ),
            {"path_kind": "messages", "body": {"embeds": [{"title": "A"}]}},
        )

    def test_embed_list_used_as_is(self) -> None:
        self.assertEqual(
            build_channel_message_payload([{"title": "A"}, {"title": "B"}], ROW),
            {
                "path_kind": "messages",
                "body": {
                    "embeds": [{"title": "A"}, {"title": "B"}],
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

    def test_empty_embed_list_with_content(self) -> None:
        self.assertEqual(
            build_channel_message_payload(
                [],
                content="hi",
                allowed_mentions={"users": ["1"]},
                message_reference={"message_id": "9", "fail_if_not_exists": False},
            ),
            {
                "path_kind": "messages",
                "body": {
                    "embeds": [],
                    "content": "hi",
                    "allowed_mentions": {"users": ["1"]},
                    "message_reference": {
                        "message_id": "9",
                        "fail_if_not_exists": False,
                    },
                },
            },
        )

    def test_none_embed_gives_empty_list(self) -> None:
        self.assertEqual(
            build_channel_message_payload(None, content="hi"),
            {"path_kind": "messages", "body": {"embeds": [], "content": "hi"}},
        )

    def test_forum_thread_truncates_name_to_100(self) -> None:
        self.assertEqual(
            build_channel_message_payload({"title": "A"}, forum_thread_name="x" * 150),
            {
                "path_kind": "threads",
                "body": {"name": "x" * 100, "message": {"embeds": [{"title": "A"}]}},
            },
        )


class BuildDmPayloadTest(SimpleTestCase):
    def test_embed_dict_and_components(self) -> None:
        self.assertEqual(
            build_dm_payload(None, {"title": "A"}, ROW),
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

    def test_embed_list_used_as_is(self) -> None:
        self.assertEqual(
            build_dm_payload("hey", [{"title": "A"}, {"title": "B"}]),
            {"content": "hey", "embeds": [{"title": "A"}, {"title": "B"}]},
        )

    def test_content_only_drops_empty(self) -> None:
        self.assertEqual(build_dm_payload("hello", None, []), {"content": "hello"})

    def test_empty_embed_dict_dropped(self) -> None:
        self.assertEqual(build_dm_payload("hi", {}), {"content": "hi"})

    def test_all_empty_gives_empty_body(self) -> None:
        self.assertEqual(build_dm_payload(None, None), {})


class PayloadSchemaTest(SimpleTestCase):
    def test_announcement_v2_shape(self) -> None:
        msg = DiscordMessage.model_validate(
            {
                "embeds": [
                    {
                        "title": "Inhouse",
                        "description": "Snacks &amp; drinks",
                        "url": "https://example.com/events/1",
                        "color": 5793266,
                        "author": {"name": "Org", "url": "https://example.com"},
                        "thumbnail": {"url": "https://example.com/logo.png"},
                        "fields": [
                            {"name": "When", "value": "<t:1:F>", "inline": True}
                        ],
                        "footer": {"text": "DraftForge"},
                        "unknown_key": "ignored",
                    }
                ],
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 3,
                                "label": "Sign Up",
                                "custom_id": "event_signup:1",
                                "emoji": {"name": "✅"},
                            },
                            {
                                "type": 2,
                                "style": 5,
                                "label": "View",
                                "url": "https://example.com/events/1",
                            },
                        ],
                    }
                ],
            }
        )
        self.assertEqual(msg.embeds[0].fields[0].name, "When")
        row = msg.components[0]
        assert isinstance(row, ActionRow)
        self.assertIsInstance(row.components[0], Button)
        self.assertEqual(row.components[1].url, "https://example.com/events/1")

    def test_v2_container_with_section_thumbnail(self) -> None:
        msg = DiscordMessage.model_validate(
            {
                "flags": 32768,
                "components": [
                    {
                        "type": 17,
                        "accent_color": 16711680,
                        "components": [
                            {
                                "type": 9,
                                "components": [{"type": 10, "content": "**Hi**"}],
                                "accessory": {
                                    "type": 11,
                                    "media": {"url": "https://example.com/a.png"},
                                },
                            },
                            {"type": 14, "divider": True},
                            {
                                "type": 1,
                                "components": [
                                    {
                                        "type": 3,
                                        "custom_id": "pick",
                                        "options": [{"label": "A", "value": "a"}],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        )
        container = msg.components[0]
        assert isinstance(container, Container)
        section = container.components[0]
        assert isinstance(section, Section)
        self.assertIsInstance(section.components[0], TextDisplay)
        self.assertIsInstance(section.accessory, Thumbnail)
        row = container.components[2]
        assert isinstance(row, ActionRow)
        self.assertIsInstance(row.components[0], SelectMenu)

    def test_container_rejects_nested_container(self) -> None:
        with self.assertRaises(ValidationError):
            DiscordMessage.model_validate(
                {"components": [{"type": 17, "components": [{"type": 17}]}]}
            )

    def test_payload_schema_imports_without_django(self) -> None:
        code = (
            "import sys; "
            f"sys.path.append({BACKEND!r}); "
            "import discordbot.payload_schema; "
            "assert 'django' not in sys.modules, 'django imported'"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_payloads_imports_without_django(self) -> None:
        code = (
            "import sys; "
            f"sys.path.append({BACKEND!r}); "
            "import discordbot.payloads; "
            "assert 'django' not in sys.modules, 'django imported'"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
