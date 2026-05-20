from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from telemetry.logging import get_logger

from .serializers import BaseUserProfileSerializer, UserProfileLayeredSerializer


log = get_logger(__name__)


class MeProfileView(APIView):
    """GET /api/users/me/profile/ — returns the layered profile shape."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        log.debug(
            "profile_fetched",
            system="user",
            subsystem="profile",
            user_id=request.user.id,
        )
        data = UserProfileLayeredSerializer(request.user).data
        return Response(data)


class MeProfileBasePatchView(APIView):
    """PATCH /api/users/me/profile/base/ — updates BaseUserProfile fields."""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = BaseUserProfileSerializer(
            instance=request.user.base_profile,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            log.warning(
                "profile_base_patch_invalid",
                system="user",
                subsystem="profile",
                user_id=request.user.id,
                errors=serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        log.info(
            "profile_base_patched",
            system="user",
            subsystem="profile",
            user_id=request.user.id,
            fields_changed=sorted(serializer.validated_data.keys()),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
