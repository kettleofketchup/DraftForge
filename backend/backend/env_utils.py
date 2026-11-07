"""Environment-variable parsing helpers shared by settings modules."""

import os


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str) -> list[str]:
    """Comma-separated env var as a list: items trimmed, empties dropped, unset -> []."""
    return [
        item.strip() for item in os.environ.get(name, "").split(",") if item.strip()
    ]
