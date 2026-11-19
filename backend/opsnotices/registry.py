import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ValidationError


class NoticeCategory(StrEnum):
    LOG = "log"
    URGENT = "urgent"
    TASK = "task"


class NoticeSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK: dict[NoticeSeverity, int] = {
    NoticeSeverity.INFO: 0,
    NoticeSeverity.WARNING: 1,
    NoticeSeverity.CRITICAL: 2,
}


@dataclass(frozen=True, slots=True)
class NoticeFact:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class NoticeLink:
    label: str
    kind: Literal["event", "member", "recovery", "external"]
    target: str


@dataclass(frozen=True, slots=True)
class NoticeDetail:
    title: str
    facts: tuple[NoticeFact, ...] = ()
    links: tuple[NoticeLink, ...] = ()


P = TypeVar("P", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class NoticeType(Generic[P]):
    key: str
    label: str
    description: str
    category: NoticeCategory
    default_severity: NoticeSeverity
    payload: type[P]
    summary: Callable[[P], str]
    sample_payload: Callable[[], P]
    detail: Callable[[P], NoticeDetail] | None = None
    dedupe_key: Callable[[P], str] | None = None
    auto_resolves: bool = False


KEY_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
SUMMARY_MAX: int = 150


class NoticeRegistryError(ValueError):
    pass


class UnknownNoticeType(NoticeRegistryError):
    pass


_REGISTRY: dict[str, NoticeType[Any]] = {}


def register_notice_type(notice_type: NoticeType[Any]) -> NoticeType[Any]:
    if not KEY_RE.match(notice_type.key):
        raise NoticeRegistryError(f"invalid notice type key: {notice_type.key!r}")
    if notice_type.key in _REGISTRY:
        raise NoticeRegistryError(f"duplicate notice type key: {notice_type.key!r}")
    _REGISTRY[notice_type.key] = notice_type
    return notice_type


def get_notice_type(key: str) -> NoticeType[Any]:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownNoticeType(f"unknown notice type: {key!r}") from None


def all_notice_types() -> list[NoticeType[Any]]:
    return [_REGISTRY[key] for key in sorted(_REGISTRY)]


def render_detail(notice_type: NoticeType[Any], payload: BaseModel) -> NoticeDetail:
    if notice_type.detail is None:
        return NoticeDetail(title=notice_type.label)
    return notice_type.detail(payload)


def _validate_type(notice_type: NoticeType[Any]) -> None:
    key = notice_type.key
    sample = notice_type.sample_payload()
    if not isinstance(sample, notice_type.payload):
        raise NoticeRegistryError(
            f"{key}: sample_payload is not a {notice_type.payload.__name__}"
        )
    try:
        notice_type.payload.model_validate(sample.model_dump(mode="json"))
    except ValidationError:
        raise NoticeRegistryError(
            f"{key}: sample_payload does not round-trip"
        ) from None
    summary = notice_type.summary(sample)
    if not isinstance(summary, str) or not summary or len(summary) > SUMMARY_MAX:
        raise NoticeRegistryError(f"{key}: summary must be 1-{SUMMARY_MAX} characters")
    if not isinstance(render_detail(notice_type, sample), NoticeDetail):
        raise NoticeRegistryError(f"{key}: detail must return NoticeDetail")
    if notice_type.auto_resolves and notice_type.dedupe_key is None:
        raise NoticeRegistryError(f"{key}: auto_resolves requires a dedupe_key hook")


def validate_registry() -> None:
    for notice_type in all_notice_types():
        _validate_type(notice_type)


@contextmanager
def isolated_registry() -> Iterator[None]:
    global _REGISTRY
    saved = _REGISTRY
    _REGISTRY = {}
    try:
        yield
    finally:
        _REGISTRY = saved
