from django.conf import settings


def namespaced_key(key: str) -> str:
    """Prefix a raw Redis key with the test-run namespace (empty in production)."""
    namespace: str = getattr(settings, "REDIS_KEY_NAMESPACE", "")
    return f"{namespace}{key}"
