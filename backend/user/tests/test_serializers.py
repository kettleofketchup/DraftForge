from django.test import TestCase

from app.models import CustomUser
from user.serializers import (
    BaseUserProfileSerializer,
    UserProfileLayeredSerializer,
)


class BaseUserProfileSerializerTests(TestCase):
    def test_serialize(self):
        user = CustomUser.objects.create(username="hans")
        user.base_profile.nickname = "Hans"
        user.base_profile.avatar = "https://example.com/h.png"
        user.base_profile.save()
        data = BaseUserProfileSerializer(user.base_profile).data
        assert data["nickname"] == "Hans"
        assert data["avatar"] == "https://example.com/h.png"

    def test_partial_update(self):
        user = CustomUser.objects.create(username="ida")
        serializer = BaseUserProfileSerializer(
            instance=user.base_profile,
            data={"nickname": "Ida New"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Ida New"


class UserProfileLayeredSerializerTests(TestCase):
    def test_layered_shape(self):
        user = CustomUser.objects.create(username="jake")
        user.base_profile.nickname = "Jake"
        user.base_profile.save()
        data = UserProfileLayeredSerializer(user).data
        assert data["pk"] == user.pk
        assert data["base"]["nickname"] == "Jake"
        assert data["gameUser"] == {}
        assert data["orgProfiles"] == {}
