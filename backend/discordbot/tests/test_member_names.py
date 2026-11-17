import ast
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase

from discordbot.services import member_names
from discordbot.services.member_names import (
    MemberNames,
    members_from_discord_payload,
    members_to_json,
    normalise_name,
)


def _member(
    user_id: Any = "42",
    username: str | None = "dc_user",
    global_name: str | None = "GwaihirTheWindlord",
    nick: str | None = "DragonClaw",
    bot: bool | None = None,
) -> dict[str, Any]:
    user: dict[str, Any] = {"username": username, "global_name": global_name}
    if user_id is not None:
        user["id"] = user_id
    if bot is not None:
        user["bot"] = bot
    return {"user": user, "nick": nick}


class NormaliseNameTests(SimpleTestCase):
    def test_none_empty_and_whitespace_become_none(self) -> None:
        self.assertIsNone(normalise_name(None))
        self.assertIsNone(normalise_name(""))
        self.assertIsNone(normalise_name("   "))
        self.assertIsNone(normalise_name("\t\n"))

    def test_real_name_is_kept(self) -> None:
        self.assertEqual(normalise_name("DragonClaw"), "DragonClaw")


class MembersFromPayloadTests(SimpleTestCase):
    def test_maps_fields(self) -> None:
        result = members_from_discord_payload([_member()])
        self.assertEqual(
            result,
            [
                MemberNames(
                    discord_id="42",
                    username="dc_user",
                    nick="DragonClaw",
                    global_name="GwaihirTheWindlord",
                )
            ],
        )

    def test_skips_bots(self) -> None:
        result = members_from_discord_payload(
            [_member(user_id="1", bot=True), _member(user_id="2", bot=False)]
        )
        self.assertEqual([m.discord_id for m in result], ["2"])

    def test_skips_entries_without_user_id(self) -> None:
        result = members_from_discord_payload(
            [_member(user_id=None), {"nick": "x"}, {"user": None}, _member()]
        )
        self.assertEqual([m.discord_id for m in result], ["42"])

    def test_empty_and_whitespace_names_become_none(self) -> None:
        result = members_from_discord_payload(
            [
                _member(user_id="1", nick="", global_name="   ", username=""),
                _member(user_id="2", nick="   ", global_name=None, username=None),
            ]
        )
        for m in result:
            self.assertIsNone(m.nick)
            self.assertIsNone(m.global_name)
            self.assertIsNone(m.username)

    def test_missing_nick_key_is_none(self) -> None:
        raw = _member()
        del raw["nick"]
        self.assertIsNone(members_from_discord_payload([raw])[0].nick)

    def test_int_id_becomes_str(self) -> None:
        result = members_from_discord_payload([_member(user_id=123456789012345678)])
        self.assertEqual(result[0].discord_id, "123456789012345678")
        self.assertIsInstance(result[0].discord_id, str)


class MembersToJsonTests(SimpleTestCase):
    def test_round_trip(self) -> None:
        members = members_from_discord_payload(
            [_member(), _member(user_id="7", nick=None, global_name=None)]
        )
        payload = members_to_json(members)
        self.assertEqual(
            payload[0],
            {
                "discord_id": "42",
                "username": "dc_user",
                "nick": "DragonClaw",
                "global_name": "GwaihirTheWindlord",
            },
        )
        self.assertEqual([MemberNames(**row) for row in payload], members)


class ModuleImportTests(SimpleTestCase):
    def test_module_imports_no_django_models(self) -> None:
        tree = ast.parse(Path(member_names.__file__).read_text())
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for name in modules:
            self.assertFalse(name.startswith("django.db"), name)
            self.assertFalse(name.startswith("cacheops"), name)
            self.assertFalse(name == "models" or name.endswith(".models"), name)
