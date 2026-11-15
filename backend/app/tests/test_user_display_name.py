from django.test import TestCase

from app.models import CustomUser


class CustomUserDisplayNameTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create_user(username="dn_user", password="x")

    def test_nickname_wins_over_discord_fields(self) -> None:
        self.user.nickname = "Site Nick"
        self.user.guildNickname = "Guild"
        self.user.discordNickname = "Global"
        self.user.discordUsername = "disc"
        self.user.save()

        self.assertEqual(self.user.display_name, "Site Nick")

    def test_username_when_no_nickname(self) -> None:
        self.user.guildNickname = "Guild"
        self.user.discordUsername = "disc"
        self.user.save()

        self.assertEqual(self.user.display_name, "dn_user")

    def test_blank_nickname_falls_back_to_username(self) -> None:
        self.user.nickname = ""

        self.assertEqual(self.user.display_name, "dn_user")

    def test_pk_fallback_without_username(self) -> None:
        self.user.username = None

        self.assertEqual(self.user.display_name, f"User {self.user.pk}")
