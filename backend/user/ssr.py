from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from app.models import CustomUser


class UserSerializerSSR(serializers.ModelSerializer):
    # nickname lives on BaseUserProfile via the OneToOne reverse
    # accessor `base_profile`. Source explicitly so DRF doesn't fall back
    # to the transitional @property and so n+1 detectors / select_related
    # callers can see the dependency.
    nickname = serializers.CharField(
        source="base_profile.nickname",
        read_only=True,
        allow_null=True,
    )
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["pk", "username", "nickname", "avatar_url"]

    def get_avatar_url(self, obj: CustomUser) -> str | None:
        return obj.avatarUrl


class UserSSRView(RetrieveAPIView):
    serializer_class = UserSerializerSSR
    permission_classes = [AllowAny]
    queryset = CustomUser.objects.all()
