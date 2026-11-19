from django.conf import settings


def namespaced_key(key: str) -> str:
    """Prefix a raw Redis key with the deployment scope and the test-run namespace.

    Both are empty in a default deployment, so keys keep their production names.
    """
    scope: str = getattr(settings, "REDIS_KEY_SCOPE", "")
    namespace: str = getattr(settings, "REDIS_KEY_NAMESPACE", "")
    return f"{scope}{namespace}{key}"
