import ipaddress
import logging
import os

from django.conf import settings
from social_core.backends.google import GooglePlusAuth
from social_core.backends.utils import load_backends

log = logging.getLogger(__name__)


def _is_ip_allowed(ip_str, allowed_ranges):
    """Check if an IP address is in any of the allowed ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for range_str in allowed_ranges:
            if "/" in range_str:
                # CIDR notation
                network = ipaddress.ip_network(range_str, strict=False)
                if ip in network:
                    return True
            else:
                # Exact IP or hostname
                if ip_str == range_str:
                    return True
        return False
    except (ipaddress.AddressValueError, ValueError):
        # If IP parsing fails, fall back to string comparison for hostnames
        return ip_str in allowed_ranges


def isTestEnvironment(request=None):
    # Fast path: bail immediately in prod
    if not settings.TEST:
        return False
    if settings.RELEASE:
        return False
    if not settings.DEBUG:
        return False
    if settings.NODE_ENV in ("prod", "release"):
        return False

    # In CI environments (GitHub Actions), skip IP validation
    ci_env = os.environ.get("CI", "").strip().lower()
    if ci_env in ("true", "1", "yes", "on"):
        return True

    # Allow requests from localhost and Docker container IP ranges
    allowed_ips = [
        "127.0.0.1",
        "localhost",
        # Docker bridge networks (172.16.0.0/12 covers all Docker defaults)
        "172.16.0.0/12",
    ]

    if request:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        remote_addr = (
            x_forwarded_for.split(",")[0].strip()
            if x_forwarded_for
            else request.META.get("REMOTE_ADDR")
        )
        # TODO(#84): Temporary logging to diagnose CI test failures
        log.warning(f"isTestEnvironment: CI={ci_env}, IP={remote_addr}")
        if remote_addr and not _is_ip_allowed(remote_addr, allowed_ips):
            return False

    return True


def is_authenticated(user):
    if callable(user.is_authenticated):
        return user.is_authenticated()
    return user.is_authenticated


def associations(user, strategy):
    user_associations = strategy.storage.user.get_social_auth_for_user(user)
    if hasattr(user_associations, "all"):
        user_associations = user_associations.all()
    return list(user_associations)


def common_context(  # fix: skip
    authentication_backends, strategy, user=None, plus_id=None, **extra
):
    """Common view context"""
    context = {
        "user": user,
        "available_backends": load_backends(authentication_backends),
        "associated": {},
    }

    if user and is_authenticated(user):
        context["associated"] = {
            association.provider: association
            for association in associations(user, strategy)
        }

    if plus_id:
        context["plus_id"] = plus_id
        context["plus_scope"] = " ".join(GooglePlusAuth.DEFAULT_SCOPE)

    return dict(context, **extra)


def url_for(name, **kwargs):
    if name == "social:begin":
        url = "/login/{backend}/"
    elif name == "social:complete":
        url = "/complete/{backend}/"
    elif name == "social:disconnect":
        url = "/disconnect/{backend}/"
    elif name == "social:disconnect_individual":
        url = "/disconnect/{backend}/{association_id}/"
    else:
        url = name
    return url.format(**kwargs)
