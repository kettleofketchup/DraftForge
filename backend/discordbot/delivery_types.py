from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChannelKind(StrEnum):
    TEXT = "text"
    ANNOUNCEMENT = "announcement"
    FORUM = "forum"


def valid_discord_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and value.strip("0") != ""
    )


@dataclass(frozen=True)
class ResolvedChannel:
    channel_id: str
    guild_id: str
    kind: ChannelKind


@dataclass(frozen=True)
class DeliveryReceipt:
    parent_channel_id: str
    message_id: str
    thread_id: str | None
    kind: ChannelKind

    def to_json(self) -> dict[str, str | None]:
        return {
            "parent_channel_id": self.parent_channel_id,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "kind": self.kind.value,
        }

    @classmethod
    def from_json(cls, data: dict) -> DeliveryReceipt:
        try:
            receipt = cls(
                parent_channel_id=data["parent_channel_id"],
                message_id=data["message_id"],
                thread_id=data["thread_id"],
                kind=ChannelKind(data["kind"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid delivery receipt") from exc
        if not valid_discord_id(receipt.parent_channel_id) or not valid_discord_id(
            receipt.message_id
        ):
            raise ValueError("Invalid delivery receipt identifiers")
        if receipt.kind == ChannelKind.FORUM:
            if not valid_discord_id(receipt.thread_id):
                raise ValueError("Forum receipt requires a thread identifier")
        elif receipt.thread_id is not None:
            raise ValueError("Text receipt cannot contain a thread identifier")
        return receipt

    def storage_channel_type(self) -> str:
        return "forum" if self.kind == ChannelKind.FORUM else "text"


class FailurePhase(StrEnum):
    CHANNEL_LOOKUP = "channel_lookup"
    CREATE = "create"
    CLAIM = "claim"
    FINALIZE = "finalize"
    BUILD = "build"


class FailureCategory(StrEnum):
    HTTP_ERROR = "http_error"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    TRANSPORT = "transport"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_CHANNEL = "unsupported_channel"
    CHANNEL_MISMATCH = "channel_mismatch"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DeliveryFailure:
    phase: FailurePhase
    category: FailureCategory
    status: int | None = None
    code: int | None = None

    def safe_json(self) -> dict[str, int | str]:
        data: dict[str, int | str] = {
            "phase": self.phase.value,
            "category": self.category.value,
        }
        if self.status is not None:
            data["status"] = self.status
        if self.code is not None:
            data["code"] = self.code
        return data

    def log_fields(self) -> dict[str, int | str | None]:
        return dict(self.safe_json())
