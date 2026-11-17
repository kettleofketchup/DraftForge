from django.test import TestCase

from app.models import CustomUser
from user.serializers import (
    BaseUserProfileSerializer,
    UserProfileLayeredSerializer,
)


class BaseUserProfileSerializerTests(TestCase):
    def test_serialize(self) -> None:
        user = CustomUser.objects.create(username="hans")
        user.base_profile.avatar = "https://example.com/h.png"
        user.base_profile.save()
        data = BaseUserProfileSerializer(user.base_profile).data
        assert "nickname" not in data
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
        user.base_profile.refresh_from_db()
        assert user.base_profile.avatar == "https://example.com/i.png"


class UserProfileLayeredSerializerTests(TestCase):
    def test_layered_shape(self) -> None:
        user = CustomUser.objects.create(username="jake")
        user = CustomUser.objects.nocache().get(pk=user.pk)
        data = UserProfileLayeredSerializer(user).data
        assert data["pk"] == user.pk
        assert "nickname" not in data["base"]
        assert set(data["gameUser"].keys()) == {"dota", "deadlock"}
        assert data["orgProfiles"] == {}
