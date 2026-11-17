"""
Pins the JSON shape of UserSerializer and TournamentUserSerializer now that
`avatar` lives on BaseUserProfile and the site nickname is retired: `nickname`
stays on the wire as null for clients that still require the key.
"""

from django.test import TestCase

from app.models import CustomUser
from app.serializers import TournamentUserSerializer, UserSerializer


class UserSerializerNicknameAvatarTests(TestCase):
    def test_avatar_in_payload_nickname_null(self) -> None:
        user = CustomUser.objects.create(username="kara")
        user.base_profile.avatar = "https://example.com/kara.png"
        user.base_profile.save()

        data = UserSerializer(user).data
        assert "nickname" not in data
        assert data["avatar"] == "https://example.com/kara.png"

    def test_nickname_and_avatar_null_when_unset(self) -> None:
        user = CustomUser.objects.create(username="lior")
        data = UserSerializer(user).data
        assert "nickname" not in data
        assert data["avatar"] is None


class TournamentUserSerializerNicknameAvatarTests(TestCase):
    def test_avatar_in_payload_nickname_null(self) -> None:
        user = CustomUser.objects.create(username="mira")
        user.base_profile.avatar = "https://example.com/mira.png"
        user.base_profile.save()

        data = TournamentUserSerializer(user).data
        assert "nickname" not in data
        assert data["avatar"] == "https://example.com/mira.png"
