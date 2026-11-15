"""Primitive codecs shared by gateway, Django and notification builders."""

from typing import Literal


def decode_draft_launch(custom_id: str) -> tuple[Literal["hero", "team"], int] | None:
    parts = custom_id.split(":")
    if (
        len(parts) != 3
        or parts[0] != "draft_activity"
        or parts[1] not in {"hero", "team"}
    ):
        return None
    if not parts[2].isascii() or not parts[2].isdigit() or not 0 < len(parts[2]) <= 18:
        return None
    draft_id = int(parts[2])
    return (parts[1], draft_id) if draft_id > 0 else None
