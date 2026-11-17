"""CustomUser.createFromDiscordData stores Discord names."""

from django.test import TestCase

from app.models import CustomUser, PositionsModel


class CreateFromDiscordDataNamesTest(TestCase):
    def setUp(self) -> None:
        self.positions = PositionsModel.objects.create()

    def _build_member(
        self,
        *,
        nick: str | None = None,
        global_name: str | None = None,
        username: str = "alice",
        user_id: str = "123",
    ) -> dict:
        return {
            "nick": nick,
            "user": {
                "id": user_id,
                "username": username,
                "global_name": global_name,
                "avatar": "abc",
            },
        }

    def _create(self, member: dict) -> CustomUser:
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(member)
        user.save()
        return user

    def test_stores_global_name_and_username(self) -> None:
        user = self._create(
            self._build_member(nick="DragonClaw", global_name="Gwaihir", username="dc")
        )
        self.assertEqual(user.discordNickname, "Gwaihir")
        self.assertEqual(user.username, "dc")

    def test_sets_discord_nickname_from_global_name(self) -> None:
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(
                nick="DragonClaw", global_name="Gwaihir", username="alice"
            )
        )
        self.assertEqual(user.discordNickname, "Gwaihir")

    def test_discord_nickname_none_without_global_name(self) -> None:
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick="DragonClaw", global_name=None, username="alice")
        )
        self.assertIsNone(user.discordNickname)

    def test_discord_nickname_none_for_whitespace_global_name(self) -> None:
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick=None, global_name="   ", username="alice")
        )
        self.assertIsNone(user.discordNickname)
