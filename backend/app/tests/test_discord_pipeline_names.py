from django.test import TestCase
from social_django.models import UserSocialAuth

from app.models import CustomUser
from app.pipelines import save_discord

DISCORD_ID = "555000111222333999"


def _social(user: CustomUser, global_name: str | None) -> UserSocialAuth:
    return UserSocialAuth.objects.create(
        user=user,
        provider="discord",
        uid=DISCORD_ID,
        extra_data={
            "id": DISCORD_ID,
            "avatar": "av",
            "username": "dragonclaw_handle",
            "global_name": global_name,
        },
    )


class SaveDiscordGlobalNameTest(TestCase):
    def test_writes_global_name(self) -> None:
        user = CustomUser.objects.create(username="fresh")
        _social(user, "Gwaihir")

        save_discord(strategy=None, details={}, user=user)

        user.refresh_from_db()
        self.assertEqual(user.discordNickname, "Gwaihir")

    def test_never_writes_site_nickname(self) -> None:
        user = CustomUser.objects.create(username="fresh")
        _social(user, "Gwaihir")

        save_discord(strategy=None, details={}, user=user)

        user = CustomUser.objects.get(pk=user.pk)
        self.assertEqual(user.discordNickname, "Gwaihir")

    def test_missing_global_name_overwrites_stored(self) -> None:
        user = CustomUser.objects.create(username="fresh", discordNickname="Old")
        _social(user, None)

        save_discord(strategy=None, details={}, user=user)

        user.refresh_from_db()
        self.assertIsNone(user.discordNickname)

    def test_whitespace_global_name_stored_as_none(self) -> None:
        user = CustomUser.objects.create(username="fresh")
        _social(user, "   ")

        save_discord(strategy=None, details={}, user=user)

        user.refresh_from_db()
        self.assertIsNone(user.discordNickname)

    def test_merged_account_gets_global_name(self) -> None:
        phantom = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        login_row = CustomUser.objects.create(username="loginrow")
        _social(login_row, "Gwaihir")

        result = save_discord(strategy=None, details={}, user=login_row)

        self.assertEqual(result["user"].pk, phantom.pk)
        phantom.refresh_from_db()
        self.assertEqual(phantom.discordNickname, "Gwaihir")
