"""
Pins compatibility of existing app/serializers.py with the
BaseUserProfile migration: legacy serializers that exposed
`nickname` / `avatar` as CustomUser model fields must keep
emitting the same JSON shape now that those fields live on
`BaseUserProfile`.

Covers the two serializers identified in T1.6:
- UserSerializer (primary identity payload — /api/users/, /api/users/me/, etc.)
- TournamentUserSerializer (used in tournament/team/league/match payloads)

The implementation may either declare the fields explicitly with
`source="base_profile.nickname"` (preferred — explicit + avoids the
property getter) or rely on the transitional @property getters on
CustomUser. Either way, the output shape must be preserved.
"""

from django.test import TestCase

from app.models import CustomUser
from app.serializers import TournamentUserSerializer, UserSerializer


class UserSerializerNicknameAvatarTests(TestCase):
    def test_nickname_in_payload(self):
        user = CustomUser.objects.create(username="kara")
        user.base_profile.nickname = "Kara Display"
        user.base_profile.avatar = "https://example.com/kara.png"
        user.base_profile.save()

        data = UserSerializer(user).data
        assert data["nickname"] == "Kara Display"
        assert data["avatar"] == "https://example.com/kara.png"

    def test_nickname_null_when_unset(self):
        user = CustomUser.objects.create(username="lior")
        # base_profile auto-created with empty defaults
        data = UserSerializer(user).data
        # BaseUserProfile.nickname/avatar are TextField(null=True) with no
        # explicit default → Django returns None, DRF serializes to JSON null.
        # Pin the exact value (not `in (None, "")`) — both representations
        # would technically pass the assertion, but only one is correct.
        assert data["nickname"] is None
        assert data["avatar"] is None


class TournamentUserSerializerNicknameAvatarTests(TestCase):
    def test_nickname_in_payload(self):
        user = CustomUser.objects.create(username="mira")
        user.base_profile.nickname = "Mira Display"
        user.base_profile.avatar = "https://example.com/mira.png"
        user.base_profile.save()

        data = TournamentUserSerializer(user).data
        assert data["nickname"] == "Mira Display"
        assert data["avatar"] == "https://example.com/mira.png"
