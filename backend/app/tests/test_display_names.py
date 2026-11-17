from django.test import SimpleTestCase, TestCase

from app.display_names import first_name, user_display_name
from app.models import CustomUser


class FirstNameTest(SimpleTestCase):
    def test_skips_none_and_blank_and_strips(self) -> None:
        self.assertEqual(first_name(None, "  ", " Drag "), "Drag")

    def test_no_candidates(self) -> None:
        self.assertIsNone(first_name())

    def test_all_blank(self) -> None:
        self.assertIsNone(first_name(None, "", "   "))


class UserDisplayNameTest(TestCase):
    def test_global_name_over_username(self) -> None:
        user = CustomUser.objects.create(username="dc", discordNickname="Gwaihir")
        self.assertEqual(user_display_name(user), "Gwaihir")

    def test_guild_nickname_wins(self) -> None:
        user = CustomUser.objects.create(username="dc", discordNickname="Gwaihir")
        self.assertEqual(
            user_display_name(user, guild_nickname="DragonClaw"), "DragonClaw"
        )

    def test_blank_guild_nickname_falls_through(self) -> None:
        user = CustomUser.objects.create(username="dc", discordNickname="Gwaihir")
        self.assertEqual(user_display_name(user, guild_nickname="  "), "Gwaihir")

    def test_empty_global_name_falls_to_username(self) -> None:
        user = CustomUser.objects.create(username="dc", discordNickname="")
        self.assertEqual(user_display_name(user), "dc")

    def test_steam_only_user(self) -> None:
        user = CustomUser.objects.create(username=None, discordNickname=None)
        self.assertEqual(user_display_name(user), f"User {user.pk}")
