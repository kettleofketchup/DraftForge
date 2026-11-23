from collections.abc import Mapping
from typing import Any

from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions
from rest_framework.request import Request

from app.models import CustomUser


class IsStaff(permissions.BasePermission):
    """
    Allows access only to authenticated staff users.
    """

    def has_permission(self, request: Request, view: object) -> bool:
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )


def request_user(context: Mapping[str, Any]) -> CustomUser | AnonymousUser:
    request = context.get("request")
    return getattr(request, "user", None) or AnonymousUser()
