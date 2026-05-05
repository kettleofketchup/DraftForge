"""Test that CustomUser.createFromDiscordData seeds nickname from guild nick → global_name → username."""

from django.test import TestCase
from app.models import CustomUser, PositionsModel


class CreateFromDiscordDataNicknameTest(TestCase):
    """Regression for #196b — new users from Discord must have a non-empty nickname."""

    def setUp(self):
        self.positions = PositionsModel.objects.create()

    def _build_member(self, *, nick=None, global_name=None, username="alice", user_id="123"):
        return {
            "nick": nick,
            "user": {
                "id": user_id,
                "username": username,
                "global_name": global_name,
                "avatar": "abc",
            },
        }

    def test_uses_guild_nick_when_present(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick="GuildNick", global_name="GlobalName", username="alice")
        )
        self.assertEqual(user.nickname, "GuildNick")

    def test_falls_back_to_global_name_when_no_nick(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick=None, global_name="GlobalName", username="alice")
        )
        self.assertEqual(user.nickname, "GlobalName")

    def test_falls_back_to_username_when_no_nick_or_global_name(self):
        """Issue #196b: nickname must be a non-empty string, never blank."""
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick=None, global_name=None, username="alice")
        )
        self.assertEqual(user.nickname, "alice")

    def test_falls_back_to_username_when_nick_and_global_name_empty_string(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick="", global_name="", username="alice")
        )
        self.assertEqual(user.nickname, "alice")
