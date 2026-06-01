"""Typed Discord component custom_id codecs (#268).

Bot-internal: these never cross the internal HTTP boundary. The Discord wire
form is the colon string produced by ``encode()`` (Discord caps custom_ids at
100 chars), NOT ``model_dump()`` JSON. Each codec reproduces the existing
custom_id strings byte-for-byte so persistent components on already-posted
messages keep working.

Single source of truth for the signup-flow prefixes: ``log_context`` derives
its tag prefixes from ``SIGNUP_TAG_PREFIXES`` below.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ValidationError


class CustomId(BaseModel):
    """Base codec: ``<PREFIX>:<event_id>``.

    Concrete subclasses MUST set ``PREFIX``. Irregular shapes (extra segments,
    slot-in-prefix) override ``encode``/``decode``/``matches``.
    """

    PREFIX: ClassVar[str]
    event_id: int
    model_config = {"frozen": True}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "PREFIX", None):
            raise TypeError(f"{cls.__name__} must set a non-empty PREFIX")

    def encode(self) -> str:
        return f"{self.PREFIX}:{self.event_id}"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return raw.startswith(f"{cls.PREFIX}:")

    @classmethod
    def decode(cls, raw: str) -> "CustomId":
        try:
            prefix, rest = raw.split(":", 1)
            if prefix != cls.PREFIX:
                raise ValueError(f"prefix mismatch: {raw!r}")
            return cls(event_id=int(rest))
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r} for {cls.__name__}") from exc


# --- Game-agnostic RSVP buttons --------------------------------------------
class SignupId(CustomId):
    PREFIX = "event_signup"


class TentativeId(CustomId):
    PREFIX = "event_tentative"


class DeclineId(CustomId):
    PREFIX = "event_decline"


class NotifyId(CustomId):
    PREFIX = "event_notify"


# --- Modal field ids -------------------------------------------------------
class SignupFriendId(CustomId):
    PREFIX = "signup_friend_id"


class SignupRankStatusId(CustomId):
    PREFIX = "signup_rank_status"


class SignupDeadlockRankId(CustomId):
    PREFIX = "signup_deadlock_rank"


class SignupDeadlockDateId(CustomId):
    PREFIX = "signup_deadlock_date"


# --- Dota follow-up components ---------------------------------------------
class PosConfirmId(CustomId):
    PREFIX = "pos_confirm"


class RankStatusId(CustomId):
    PREFIX = "rank_status"


class RankMedalId(CustomId):
    PREFIX = "rank_medal"


class BattleCupTierId(CustomId):
    PREFIX = "bcup_tier"


class PosSelectId(CustomId):
    """Irregular: the slot lives in the prefix — ``pos_select_<slot>:<event_id>``."""

    PREFIX = "pos_select"
    slot: int

    def encode(self) -> str:
        return f"{self.PREFIX}_{self.slot}:{self.event_id}"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return raw.startswith(f"{cls.PREFIX}_")

    @classmethod
    def decode(cls, raw: str) -> "PosSelectId":
        try:
            head, ev = raw.split(":", 1)
            slot = int(head[len(cls.PREFIX) + 1 :])  # strip "pos_select_"
            return cls(event_id=int(ev), slot=slot)
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r} for {cls.__name__}") from exc


class RankStarId(CustomId):
    """``rank_star:<event_id>:<medal>`` — the picked medal is encoded in the id."""

    PREFIX = "rank_star"
    medal: str

    def encode(self) -> str:
        return f"{self.PREFIX}:{self.event_id}:{self.medal}"

    @classmethod
    def decode(cls, raw: str) -> "RankStarId":
        try:
            prefix, ev, medal = raw.split(":", 2)
            if prefix != cls.PREFIX:
                raise ValueError(f"prefix mismatch: {raw!r}")
            return cls(event_id=int(ev), medal=medal)
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r} for {cls.__name__}") from exc


class _ScreenshotId(CustomId):
    """``<PREFIX>:<event_id>:<screenshot_type>`` — shared by the upload/file/url ids.

    Not used directly; concrete subclasses set PREFIX. (PREFIX is set here only
    so the base passes the __init_subclass__ guard; subclasses override it.)
    """

    PREFIX = "screenshot"
    screenshot_type: str

    def encode(self) -> str:
        return f"{self.PREFIX}:{self.event_id}:{self.screenshot_type}"

    @classmethod
    def decode(cls, raw: str) -> "_ScreenshotId":
        try:
            prefix, ev, stype = raw.split(":", 2)
            if prefix != cls.PREFIX:
                raise ValueError(f"prefix mismatch: {raw!r}")
            return cls(event_id=int(ev), screenshot_type=stype)
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r} for {cls.__name__}") from exc


class ScreenshotUploadId(_ScreenshotId):
    PREFIX = "screenshot_upload"


class ScreenshotFileId(_ScreenshotId):
    PREFIX = "screenshot_file"


class ScreenshotUrlId(_ScreenshotId):
    PREFIX = "screenshot_url"


# Registry for log_context tag derivation + tests.
ALL_CODECS: tuple[type[CustomId], ...] = (
    SignupId,
    TentativeId,
    DeclineId,
    NotifyId,
    SignupFriendId,
    SignupRankStatusId,
    SignupDeadlockRankId,
    SignupDeadlockDateId,
    PosSelectId,
    PosConfirmId,
    RankStatusId,
    RankMedalId,
    BattleCupTierId,
    RankStarId,
    ScreenshotUploadId,
    ScreenshotFileId,
    ScreenshotUrlId,
)

# Prefixes that map to the ["events", "signup"] log tags (see log_context).
SIGNUP_TAG_PREFIXES: frozenset[str] = frozenset(c.PREFIX for c in ALL_CODECS)
