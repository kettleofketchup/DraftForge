"""Internal service authentication for celery workers and Discord bot.

External processes communicate with Django via HTTP instead of accessing the
database directly. Authentication uses a shared secret token passed in the
X-Internal-Token header, compared with hmac.compare_digest() for timing safety.

Security layers:
- Timing-safe token comparison (hmac.compare_digest)
- IP whitelist (INTERNAL_SERVICE_ALLOWED_IPS, defaults to Docker networks + localhost)
- is_staff=False: internal token must NOT grant access to staff-only endpoints
- pk=-1: sentinel that never matches real user PKs in DRF serializers
- Failed auth attempts are logged for monitoring
"""

import hmac
import logging

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

# Default allowed IPs: localhost + Docker bridge networks
DEFAULT_ALLOWED_IPS = [
    "127.0.0.1",
    "::1",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
]


def _get_client_ip(request):
    """Extract client IP from request, handling proxy headers."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _ip_in_allowlist(ip, allowed):
    """Check if IP matches any entry in the allowlist (supports CIDR)."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for entry in allowed:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


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
    """Authenticate via X-Internal-Token header + IP whitelist."""

    def authenticate(self, request):
        token = (
            request.headers.get("X-Internal-Token")
            or request.META.get("HTTP_X_INTERNAL_TOKEN")
            or ""
        )
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected or not token:
            return None

        # IP whitelist check
        allowed_ips = (
            getattr(settings, "INTERNAL_SERVICE_ALLOWED_IPS", None)
            or DEFAULT_ALLOWED_IPS
        )
        client_ip = _get_client_ip(request)
        if not _ip_in_allowlist(client_ip, allowed_ips):
            logger.warning("Internal auth rejected: IP %s not in allowlist", client_ip)
            return None

        # Token comparison (timing-safe)
        if hmac.compare_digest(token, expected):
            return (InternalServiceUser(), None)

        logger.warning("Internal auth failed: invalid token from IP %s", client_ip)
        return None


class IsInternalService(BasePermission):
    """Allow only authenticated internal service requests."""

    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
