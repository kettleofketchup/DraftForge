"""ORM-free mapping of Discord guild member payloads to name fields.

Imported by celery tasks, so it must stay free of Django models and cacheops.
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MemberNames:
    discord_id: str
    username: str | None
    nick: str | None
    global_name: str | None


def normalise_name(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def members_from_discord_payload(raw: list[dict[str, Any]]) -> list[MemberNames]:
    members: list[MemberNames] = []
    for entry in raw:
        user = entry.get("user") or {}
        user_id = user.get("id")
        if user_id is None or user.get("bot"):
            continue
        members.append(
            MemberNames(
                discord_id=str(user_id),
                username=normalise_name(user.get("username")),
                nick=normalise_name(entry.get("nick")),
                global_name=normalise_name(user.get("global_name")),
            )
        )
    return members


def members_to_json(members: list[MemberNames]) -> list[dict[str, str | None]]:
    return [asdict(member) for member in members]
