"""Pure Discord message bodies, shared by the send primitives and previews.

Django-free and HTTP-free.
"""

import hashlib
import json
from typing import Any, Literal, TypedDict

JSONDict = dict[str, Any]
V2_FLAG: int = 1 << 15


def live_component_digest(components: list[JSONDict]) -> str:
    """Hash what the live editor can replace, independently of key order."""
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class ChannelMessagePayload(TypedDict):
    path_kind: Literal["messages", "threads"]
    body: JSONDict


def _embed_list(embed: JSONDict | list[JSONDict] | None) -> list[JSONDict]:
    if embed is None:
        return []
    return embed if isinstance(embed, list) else [embed]


def build_channel_message_payload(
    embed: JSONDict | list[JSONDict] | None,
    components: list[JSONDict] | None = None,
    content: str | None = None,
    allowed_mentions: JSONDict | None = None,
    message_reference: JSONDict | None = None,
    forum_thread_name: str | None = None,
) -> ChannelMessagePayload:
    message: JSONDict = {"embeds": _embed_list(embed)}
    if components:
        message["components"] = components
    if content:
        message["content"] = content
    if allowed_mentions:
        message["allowed_mentions"] = allowed_mentions
    if message_reference:
        message["message_reference"] = message_reference

    if forum_thread_name:
        return {
            "path_kind": "threads",
            "body": {"name": forum_thread_name[:100], "message": message},
        }
    return {"path_kind": "messages", "body": message}


def build_dm_payload(
    content: str | None,
    embed: JSONDict | list[JSONDict] | None,
    components: list[JSONDict] | None = None,
) -> JSONDict:
    payload: JSONDict = {}
    if content:
        payload["content"] = content
    embeds = embed if isinstance(embed, list) else [embed] if embed else []
    if embeds:
        payload["embeds"] = embeds
    if components:
        payload["components"] = components
    return payload
