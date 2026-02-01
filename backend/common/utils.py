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
    # TODO(#84): Temporary WARNING level logging to diagnose CI test failures.
    # These should be changed back to DEBUG level once auth.ts tests pass in CI.
    log.warning(f"isTestEnvironment called: TEST={settings.TEST}, RELEASE={settings.RELEASE}, DEBUG={settings.DEBUG}, NODE_ENV={settings.NODE_ENV}, CI={os.environ.get('CI')}")

    if not settings.TEST:
        log.warning("isTestEnvironment: TEST is not True")
        return False
    if settings.RELEASE:
        log.warning("isTestEnvironment: RELEASE is True")
        return False
    if not settings.DEBUG:
        log.warning("isTestEnvironment: DEBUG is not True")
        return False
    if settings.NODE_ENV == "prod":
        log.warning("isTestEnvironment: NODE_ENV is 'prod'")
        return False
    if settings.NODE_ENV == "release":
        log.warning("isTestEnvironment: NODE_ENV is 'release'")
        return False

    # In CI environments (GitHub Actions), skip IP validation
    # All other security checks above still apply (TEST, DEBUG, NODE_ENV)
    ci_env = os.environ.get("CI", "").strip().lower()
    log.warning(f"isTestEnvironment: CI environment variable = '{ci_env}' (original: '{os.environ.get('CI')}')")
    if ci_env in ("true", "1", "yes", "on"):
        log.warning("isTestEnvironment: CI is truthy, returning True")
        return True

    # Allow requests from localhost and common Docker container IP ranges
    allowed_ips = [
        "127.0.0.1",
        "localhost",
        # Docker default bridge network range
        "172.17.0.0/16",
        # Docker compose default network ranges
        "172.18.0.0/16",
        "172.19.0.0/16",
        "172.20.0.0/16",
        "172.21.0.0/16",
        "172.22.0.0/16",
        "172.23.0.0/16",
        "172.24.0.0/16",
        "172.25.0.0/16",
        # Common custom Docker networks
        "192.168.0.0/16",
        "10.0.0.0/8",
    ]

    if request:
        # Use X-Forwarded-For if behind proxy (e.g., Nginx), otherwise REMOTE_ADDR
        # X-Forwarded-For can contain multiple IPs; the first is the original client
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if x_forwarded_for:
            remote_addr = x_forwarded_for.split(",")[0].strip()
        else:
            remote_addr = request.META.get("REMOTE_ADDR")
        log.warning(f"isTestEnvironment: Checking IP - X-Forwarded-For='{x_forwarded_for}', REMOTE_ADDR='{request.META.get('REMOTE_ADDR')}', remote_addr='{remote_addr}'")
        if remote_addr and not _is_ip_allowed(remote_addr, allowed_ips):
            log.warning(f"isTestEnvironment: IP '{remote_addr}' not in allowed list, returning False")
            return False

    log.warning("isTestEnvironment: All checks passed, returning True")
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
