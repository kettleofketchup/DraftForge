from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
