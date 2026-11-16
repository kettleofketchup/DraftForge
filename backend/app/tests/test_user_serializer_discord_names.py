import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from app.serializers import UserSerializer
from app.tests.raw_site_nickname import raw_guild_nickname, raw_site_nickname

BACKEND_DIR = Path(settings.BASE_DIR)


class UserSerializerDiscordNamesTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create_user(
            username="usd_user", password="x", discordNickname="Gwaihir"
        )

    def test_emits_discord_nickname_not_guild_nickname(self) -> None:
        data = UserSerializer(self.user).data
        self.assertNotIn("guildNickname", data)
        self.assertEqual(data["discordNickname"], "Gwaihir")

    def test_create_stores_discord_nickname(self) -> None:
        serializer = UserSerializer(
            data={"username": "usd_new", "discordNickname": "NewGlobal"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(
            CustomUser.objects.nocache().get(pk=user.pk).discordNickname, "NewGlobal"
        )

    def test_update_ignores_discord_nickname(self) -> None:
        serializer = UserSerializer(
            self.user,
            data={"discordNickname": "Hijack", "nickname": "Site"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        fresh = CustomUser.objects.nocache().get(pk=self.user.pk)
        self.assertEqual(fresh.discordNickname, "Gwaihir")
        self.assertIsNone(raw_site_nickname(self.user.pk))

    def test_update_ignores_guild_nickname(self) -> None:
        serializer = UserSerializer(
            self.user, data={"guildNickname": "Manual"}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertIsNone(raw_guild_nickname(self.user.pk))

    def test_register_view_stores_client_global_name(self) -> None:
        staff = CustomUser.objects.create_user(
            username="usd_staff", password="x", is_staff=True
        )
        client = APIClient()
        client.force_authenticate(user=staff)
        resp = client.post(
            "/api/user/register",
            {"username": "usd_reg", "discordId": "777", "discordNickname": "Reg"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(
            CustomUser.objects.nocache().get(username="usd_reg").discordNickname,
            "Reg",
        )


class NoSerializerEmitsCustomUserGuildNicknameTest(TestCase):
    def test_no_serializer_emits_customuser_guildnickname(self) -> None:
        offenders: list[str] = []
        for path in BACKEND_DIR.rglob("serializers*.py"):
            parts = set(path.parts)
            if "tests" in parts or "migrations" in parts or ".venv" in parts:
                continue
            text = path.read_text()
            if 'source="user.guildNickname"' in text:
                offenders.append(f"{path}: source=user.guildNickname")
            for match in re.finditer(r'"guildNickname"', text):
                line = text[: match.start()].count("\n") + 1
                line_text = text.splitlines()[line - 1]
                if 'source="guild_nickname"' in line_text:
                    continue
                if _in_customuser_meta(text, match.start()):
                    offenders.append(f"{path}:{line}")
        self.assertEqual(offenders, [])


def _in_customuser_meta(text: str, pos: int) -> bool:
    meta = text.rfind("class Meta", 0, pos)
    if meta == -1:
        return False
    if re.search(r"\n\S", text[meta:pos]):
        return False
    model_line = re.search(r"model\s*=\s*(\w+)", text[meta:pos])
    if not (model_line and model_line.group(1) == "CustomUser"):
        return False
    body = text[text.rfind("\nclass ", 0, meta) : meta]
    return "guildNickname = serializers.SerializerMethodField(" not in body
