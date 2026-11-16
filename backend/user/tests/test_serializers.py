from django.db import connection
from django.test import TestCase

from app.models import CustomUser
from user.serializers import (
    BaseUserProfileSerializer,
    UserProfileLayeredSerializer,
)


def set_raw_site_nickname(user_id: int, value: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE user_baseuserprofile SET nickname=%s WHERE user_id=%s",
            [value, user_id],
        )


def raw_site_nickname(user_id: int) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nickname FROM user_baseuserprofile WHERE user_id=%s", [user_id]
        )
        return cursor.fetchone()[0]


class BaseUserProfileSerializerTests(TestCase):
    def test_serialize(self) -> None:
        user = CustomUser.objects.create(username="hans")
        user.base_profile.avatar = "https://example.com/h.png"
        user.base_profile.save()
        set_raw_site_nickname(user.pk, "Hans")
        data = BaseUserProfileSerializer(user.base_profile).data
        assert data["nickname"] is None
        assert data["avatar"] == "https://example.com/h.png"

    def test_partial_update_ignores_nickname(self) -> None:
        user = CustomUser.objects.create(username="ida")
        serializer = BaseUserProfileSerializer(
            instance=user.base_profile,
            data={"nickname": "Ida New", "avatar": "https://example.com/i.png"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert "nickname" not in serializer.validated_data
        assert raw_site_nickname(user.pk) is None
        user.base_profile.refresh_from_db()
        assert user.base_profile.avatar == "https://example.com/i.png"


class UserProfileLayeredSerializerTests(TestCase):
    def test_layered_shape(self) -> None:
        user = CustomUser.objects.create(username="jake")
        set_raw_site_nickname(user.pk, "Jake")
        user = CustomUser.objects.nocache().get(pk=user.pk)
        data = UserProfileLayeredSerializer(user).data
        assert data["pk"] == user.pk
        assert data["base"]["nickname"] is None
        assert set(data["gameUser"].keys()) == {"dota", "deadlock"}
        assert data["orgProfiles"] == {}
