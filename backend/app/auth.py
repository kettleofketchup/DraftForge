"""Internal service authentication for celery workers and Discord bot.

External processes communicate with Django via HTTP instead of accessing the
database directly. Authentication uses a shared secret token passed in the
X-Internal-Token header, compared with hmac.compare_digest() for timing safety.

is_staff=False: internal token must NOT grant access to staff-only endpoints.
pk=-1: sentinel that never matches real user PKs in DRF serializers.
"""

import hmac

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission


class InternalServiceUser:
    """Sentinel user for authenticated internal service requests."""

    is_authenticated = True
    is_staff = False
    is_superuser = False
    pk = -1
    username = "_internal_service"

    def __str__(self):
        return self.username


class InternalServiceAuth(BaseAuthentication):
    """Authenticate via X-Internal-Token header (timing-safe comparison)."""

    def authenticate(self, request):
        token = (
            request.headers.get("X-Internal-Token")
            or request.META.get("HTTP_X_INTERNAL_TOKEN")
            or ""
        )
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected or not token:
            return None
        if hmac.compare_digest(token, expected):
            return (InternalServiceUser(), None)
        return None


class IsInternalService(BasePermission):
    """Allow only authenticated internal service requests."""

    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
