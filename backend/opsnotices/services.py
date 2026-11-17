from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from pydantic import BaseModel, ValidationError

from app.models import CustomUser, Organization
from events.models import Event
from opsnotices.models import OpsNotice
from opsnotices.registry import (
    NoticeSeverity,
    NoticeType,
    UnknownNoticeType,
    get_notice_type,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

DEDUPE_KEY_MAX: int = 200
_DUMMY_ENGINE: str = "django.db.backends.dummy"

_Outcome = Literal["created", "repeated", "replayed"]


class NoticeEmitError(ValueError):
    def __init__(self, code: str, notice_key: str, message: str | None = None) -> None:
        self.code: str = code
        self.notice_key: str = notice_key
        super().__init__(message or f"{code}: {notice_key}")


class NoticePayloadError(NoticeEmitError):
    def __init__(self, notice_key: str, errors: list[dict[str, Any]]) -> None:
        self.errors: list[dict[str, Any]] = errors
        super().__init__(
            "invalid_payload",
            notice_key,
            f"invalid_payload: {notice_key} ({len(errors)} errors)",
        )


@dataclass(frozen=True, slots=True)
class EventRef:
    id: int
    name: str
    event_repeater_id: int | None = None


@dataclass(frozen=True, slots=True)
class _Prepared:
    notice_type: NoticeType[Any]
    payload: dict[str, Any]
    severity: NoticeSeverity
    dedupe_key: str
    event: Event | None
    event_key: int
    event_name: str
    event_repeater_id: int | None


def _require_database(caller: str) -> None:
    engine = settings.DATABASES.get("default", {}).get("ENGINE", _DUMMY_ENGINE)
    if engine == _DUMMY_ENGINE:
        raise RuntimeError(
            f"{caller} needs a database; Celery code must call "
            "app.internal_client.emit_ops_notice"
        )


def _find_open_notice(
    organization_id: int, key: str, event_key: int, dedupe_key: str
) -> OpsNotice | None:
    return OpsNotice.objects.filter(
        organization_id=organization_id,
        key=key,
        event_key=event_key,
        dedupe_key=dedupe_key,
        closed_at__isnull=True,
    ).first()


def _validate_payload(
    notice_type: NoticeType[Any], payload: BaseModel | Mapping[str, Any]
) -> BaseModel:
    if isinstance(payload, BaseModel):
        if not isinstance(payload, notice_type.payload):
            raise NoticePayloadError(
                notice_type.key, [{"loc": (), "type": "model_type"}]
            )
        return payload
    try:
        return notice_type.payload.model_validate(payload)
    except ValidationError as exc:
        errors = [
            {"loc": error["loc"], "type": error["type"]}
            for error in exc.errors(include_url=False, include_context=False)
        ]
        raise NoticePayloadError(notice_type.key, errors) from None


def _prepare(
    key: str,
    payload: BaseModel | Mapping[str, Any],
    organization: Organization,
    event: Event | EventRef | None,
    dedupe_key: str | None,
    severity: NoticeSeverity | str | None,
) -> _Prepared:
    try:
        notice_type = get_notice_type(key)
    except UnknownNoticeType:
        raise NoticeEmitError("unknown_notice_type", key) from None

    model = _validate_payload(notice_type, payload)

    if severity is None:
        resolved_severity = notice_type.default_severity
    else:
        try:
            resolved_severity = NoticeSeverity(severity)
        except ValueError:
            raise NoticeEmitError("invalid_severity", key) from None

    if dedupe_key is not None:
        resolved_dedupe = dedupe_key
    elif notice_type.dedupe_key is not None:
        resolved_dedupe = notice_type.dedupe_key(model)
    else:
        resolved_dedupe = ""
    if len(resolved_dedupe) > DEDUPE_KEY_MAX:
        raise NoticeEmitError("dedupe_key_too_long", key)

    fk: Event | None = None
    event_key, event_name, repeater_id = 0, "", None
    if isinstance(event, Event):
        if event.organization_id != organization.id:
            raise NoticeEmitError("event_org_mismatch", key)
        fk = event
    if event is not None:
        event_key, event_name = event.id, event.name
        repeater_id = event.event_repeater_id
    return _Prepared(
        notice_type=notice_type,
        payload=model.model_dump(mode="json"),
        severity=resolved_severity,
        dedupe_key=resolved_dedupe,
        event=fk,
        event_key=event_key,
        event_name=event_name,
        event_repeater_id=repeater_id,
    )


def _bump(
    existing: OpsNotice,
    prepared: _Prepared,
    has_event: bool,
    subject_user: CustomUser | None,
    actor: CustomUser | None,
    emit_id: UUID | None,
) -> OpsNotice:
    severity = max(
        NoticeSeverity(existing.severity), prepared.severity, key=lambda s: s.rank
    )
    changes: dict[str, Any] = {
        "occurrences": F("occurrences") + 1,
        "last_seen_at": timezone.now(),
        "payload": prepared.payload,
        "actor": actor,
        "subject_user": subject_user,
        "severity": severity.value,
    }
    if emit_id is not None:
        changes["last_emit_id"] = emit_id
    if has_event:
        changes["event_name"] = prepared.event_name
        changes["event_repeater_id"] = prepared.event_repeater_id
    OpsNotice.objects.filter(pk=existing.pk).update(**changes)
    existing.refresh_from_db()
    return existing


def _write(
    prepared: _Prepared,
    organization: Organization,
    has_event: bool,
    subject_user: CustomUser | None,
    actor: CustomUser | None,
    emit_id: UUID | None,
) -> tuple[OpsNotice, _Outcome]:
    key = prepared.notice_type.key
    if emit_id is not None:
        replay = OpsNotice.objects.filter(
            organization_id=organization.id, last_emit_id=emit_id
        ).first()
        if replay is not None:
            return replay, "replayed"

    if prepared.dedupe_key:
        existing = _find_open_notice(
            organization.id, key, prepared.event_key, prepared.dedupe_key
        )
        if existing is not None:
            return _bump(
                existing, prepared, has_event, subject_user, actor, emit_id
            ), "repeated"

    try:
        with transaction.atomic():
            notice = OpsNotice.objects.create(
                organization=organization,
                event=prepared.event,
                event_key=prepared.event_key,
                event_name=prepared.event_name,
                event_repeater_id=prepared.event_repeater_id,
                subject_user=subject_user,
                actor=actor,
                key=key,
                category=prepared.notice_type.category.value,
                severity=prepared.severity.value,
                payload=prepared.payload,
                dedupe_key=prepared.dedupe_key,
                last_emit_id=emit_id,
            )
        return notice, "created"
    except IntegrityError:
        if not prepared.dedupe_key:
            raise
    existing = _find_open_notice(
        organization.id, key, prepared.event_key, prepared.dedupe_key
    )
    if existing is None:
        raise NoticeEmitError("event_conflict", key)
    return _bump(
        existing, prepared, has_event, subject_user, actor, emit_id
    ), "repeated"


def _hand_off(notice: OpsNotice, created: bool) -> None:
    return None


def _log_failure(exc: NoticeEmitError, organization: Organization | None) -> None:
    fields: dict[str, Any] = {}
    if isinstance(exc, NoticePayloadError):
        first = exc.errors[0] if exc.errors else {"loc": (), "type": ""}
        fields = {
            "error_count": len(exc.errors),
            "first_error_loc": ".".join(str(part) for part in first["loc"]),
            "first_error_type": first["type"],
        }
    log.error(
        "ops_notice_emit_failed",
        system="opsnotices",
        subsystem="emit",
        code=exc.code,
        notice_key=exc.notice_key,
        organization_id=getattr(organization, "id", None),
        **fields,
    )


def emit_notice(
    key: str,
    payload: BaseModel | Mapping[str, Any],
    *,
    organization: Organization,
    event: Event | EventRef | None = None,
    subject_user: CustomUser | None = None,
    actor: CustomUser | None = None,
    dedupe_key: str | None = None,
    severity: NoticeSeverity | str | None = None,
    emit_id: UUID | None = None,
    strict: bool | None = None,
) -> OpsNotice | None:
    _require_database("emit_notice")
    is_strict = settings.OPS_NOTICES_STRICT if strict is None else strict
    try:
        prepared = _prepare(key, payload, organization, event, dedupe_key, severity)
        try:
            with transaction.atomic():
                notice, outcome = _write(
                    prepared,
                    organization,
                    event is not None,
                    subject_user,
                    actor,
                    emit_id,
                )
                if outcome != "replayed":
                    _hand_off(notice, outcome == "created")
        except DatabaseError as exc:
            raise NoticeEmitError("database_error", key) from exc
    except NoticeEmitError as exc:
        if is_strict:
            raise
        _log_failure(exc, organization)
        return None

    if outcome == "created":
        log.info(
            "ops_notice_emitted",
            system="opsnotices",
            subsystem="emit",
            notice_id=notice.pk,
            notice_key=key,
            category=notice.category,
            severity=notice.severity,
            organization_id=organization.id,
            event_id=prepared.event_key or None,
            dedupe=bool(prepared.dedupe_key),
        )
    elif outcome == "repeated":
        log.debug(
            "ops_notice_repeated",
            system="opsnotices",
            subsystem="emit",
            notice_id=notice.pk,
            notice_key=key,
            occurrences=notice.occurrences,
        )
    return notice
