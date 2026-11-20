import os
import subprocess
import sys
import uuid
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.db import DatabaseError, IntegrityError, transaction
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from pydantic import BaseModel, field_serializer, field_validator
from structlog.testing import capture_logs

from events.models import Event, EventRepeater
from events.tests.base import EventTestCase
from opsnotices import services
from opsnotices.models import OpsNotice
from opsnotices.registry import (
    NoticeCategory,
    NoticeSeverity,
    NoticeType,
    isolated_registry,
    register_notice_type,
)
from opsnotices.services import (
    DEDUPE_KEY_MAX,
    EventRef,
    NoticeEmitError,
    NoticePayloadError,
    emit_notice,
)
from opsnotices.tests.types import AlertPayload, register_test_types
from org.models import Organization

BACKEND_DIR = Path(__file__).resolve().parents[2]
SENTINEL = "SENTINEL-xyz"


class SentinelPayload(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _reject(cls, value: str) -> str:
        raise ValueError(f"{SENTINEL} {value}")


class StampPayload(BaseModel):
    at: datetime
    ref: uuid.UUID


class TypeErrorPayload(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _explode(cls, value: str) -> str:
        raise TypeError(f"{SENTINEL} {value}")


class SerializerPayload(BaseModel):
    name: str

    @field_serializer("name")
    def _explode(self, value: str) -> str:
        if value == "sample":
            return value
        raise KeyError(f"{SENTINEL} {value}")


class AnyPayload(BaseModel):
    value: Any


def _raising_hook(payload: AlertPayload) -> str:
    raise KeyError(f"{SENTINEL} {payload.reason}")


def _non_str_hook(payload: AlertPayload) -> str:
    return payload.member_id  # type: ignore[return-value]


def _register_extra_types() -> None:
    register_notice_type(
        NoticeType(
            key="test.sentinel",
            label="Sentinel",
            description="Validator leaks input",
            category=NoticeCategory.URGENT,
            default_severity=NoticeSeverity.INFO,
            payload=SentinelPayload,
            summary=lambda p: "sentinel",
            sample_payload=lambda: SentinelPayload.model_construct(name="x"),
        )
    )
    register_notice_type(
        NoticeType(
            key="test.stamp",
            label="Stamp",
            description="Non JSON-native fields",
            category=NoticeCategory.LOG,
            default_severity=NoticeSeverity.INFO,
            payload=StampPayload,
            summary=lambda p: "stamp",
            sample_payload=lambda: StampPayload(at=datetime.now(UTC), ref=uuid.uuid4()),
        )
    )
    register_notice_type(
        NoticeType(
            key="test.typeerror",
            label="TypeError",
            description="Validator raises TypeError",
            category=NoticeCategory.LOG,
            default_severity=NoticeSeverity.INFO,
            payload=TypeErrorPayload,
            summary=lambda p: "typeerror",
            sample_payload=lambda: TypeErrorPayload.model_construct(name="x"),
        )
    )
    register_notice_type(
        NoticeType(
            key="test.serializer",
            label="Serializer",
            description="Field serializer raises",
            category=NoticeCategory.LOG,
            default_severity=NoticeSeverity.INFO,
            payload=SerializerPayload,
            summary=lambda p: "serializer",
            sample_payload=lambda: SerializerPayload(name="sample"),
        )
    )
    register_notice_type(
        NoticeType(
            key="test.anyvalue",
            label="Any value",
            description="Any-typed field",
            category=NoticeCategory.LOG,
            default_severity=NoticeSeverity.INFO,
            payload=AnyPayload,
            summary=lambda p: "any",
            sample_payload=lambda: AnyPayload(value=1),
        )
    )
    for hook_key, hook in (
        ("test.badhook", _raising_hook),
        ("test.nonstrhook", _non_str_hook),
    ):
        register_notice_type(
            NoticeType(
                key=hook_key,
                label=hook_key,
                description="Broken dedupe hook",
                category=NoticeCategory.URGENT,
                default_severity=NoticeSeverity.INFO,
                payload=AlertPayload,
                summary=lambda p: "hook",
                sample_payload=lambda: AlertPayload(member_id=1, reason="x"),
                dedupe_key=hook,
            )
        )


def _alert(member_id: int = 1, reason: str = "late") -> dict[str, Any]:
    return {"member_id": member_id, "reason": reason}


class EmitTestBase(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        _register_extra_types()

    def _failed_logs(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [entry for entry in logs if entry["event"] == "ops_notice_emit_failed"]

    def _repeater(self) -> EventRepeater:
        return EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency="weekly",
            time_of_day=time(19, 0),
            starts_at=timezone.now().date(),
        )

    def _event(self, name: str, organization: Organization | None = None) -> Event:
        return Event.objects.create(
            organization=organization or self.org,
            name=name,
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.admin,
        )


class FailureTriggers(EmitTestBase):
    def _triggers(self) -> list[tuple[str, Callable[[], object]]]:
        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        foreign_event = self._event("Foreign", organization=other_org)
        org = self.org

        def db_error() -> object:
            with patch.object(OpsNotice.objects, "create", side_effect=DatabaseError):
                return emit_notice("test.alert", _alert(), organization=org)

        return [
            (
                "unknown_notice_type",
                lambda: emit_notice("test.nope", {}, organization=org),
            ),
            (
                "invalid_payload",
                lambda: emit_notice("test.alert", {"member_id": "x"}, organization=org),
            ),
            (
                "invalid_severity",
                lambda: emit_notice(
                    "test.alert", _alert(), organization=org, severity="loud"
                ),
            ),
            (
                "dedupe_key_too_long",
                lambda: emit_notice(
                    "test.alert", _alert(), organization=org, dedupe_key="k" * 201
                ),
            ),
            (
                "event_org_mismatch",
                lambda: emit_notice(
                    "test.alert", _alert(), organization=org, event=foreign_event
                ),
            ),
            ("database_error", db_error),
            (
                "invalid_payload",
                lambda: emit_notice(
                    "test.typeerror", {"name": "member-name"}, organization=org
                ),
            ),
            (
                "invalid_payload",
                lambda: emit_notice(
                    "test.alert",
                    AlertPayload.model_construct(member_id="x", reason="r"),
                    organization=org,
                ),
            ),
            (
                "invalid_dedupe_key",
                lambda: emit_notice("test.badhook", _alert(), organization=org),
            ),
            (
                "invalid_dedupe_key",
                lambda: emit_notice("test.nonstrhook", _alert(), organization=org),
            ),
            (
                "invalid_dedupe_key",
                lambda: emit_notice(
                    "test.alert",
                    _alert(),
                    organization=org,
                    dedupe_key=5,  # type: ignore[arg-type]
                ),
            ),
            (
                "invalid_payload",
                lambda: emit_notice(
                    "test.serializer", {"name": "member-name"}, organization=org
                ),
            ),
            (
                "invalid_payload",
                lambda: emit_notice(
                    "test.anyvalue", {"value": object()}, organization=org
                ),
            ),
        ]


class StrictFailureTests(FailureTriggers):
    def test_each_failure_raises_with_code(self) -> None:
        for index, (code, trigger) in enumerate(self._triggers()):
            with self.subTest(index=index, code=code):
                with self.assertRaises(NoticeEmitError) as ctx:
                    trigger()
                self.assertEqual(ctx.exception.code, code)
                self.assertTrue(ctx.exception.notice_key)
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_database_error_is_chained(self) -> None:
        error = DatabaseError("boom")
        with (
            patch.object(OpsNotice.objects, "create", side_effect=error),
            self.assertRaises(NoticeEmitError) as ctx,
        ):
            emit_notice("test.alert", _alert(), organization=self.org)
        self.assertEqual(ctx.exception.code, "database_error")
        self.assertIs(ctx.exception.__cause__, error)

    def test_strict_argument_overrides_setting(self) -> None:
        with (
            override_settings(OPS_NOTICES_STRICT=False),
            self.assertRaises(NoticeEmitError),
        ):
            emit_notice("test.nope", {}, organization=self.org, strict=True)
        self.assertIsNone(
            emit_notice("test.nope", {}, organization=self.org, strict=False)
        )

    def test_payload_error_carries_only_loc_and_type(self) -> None:
        with self.assertRaises(NoticePayloadError) as ctx:
            emit_notice("test.alert", {"member_id": "x"}, organization=self.org)
        exc = ctx.exception
        self.assertEqual(exc.code, "invalid_payload")
        self.assertEqual(len(exc.errors), 2)
        for error in exc.errors:
            self.assertEqual(set(error), {"loc", "type"})
        self.assertEqual(
            {tuple(e["loc"]) for e in exc.errors}, {("member_id",), ("reason",)}
        )

    def test_dedupe_hook_failure_is_chained(self) -> None:
        with self.assertRaises(NoticeEmitError) as ctx:
            emit_notice("test.badhook", _alert(), organization=self.org)
        self.assertEqual(ctx.exception.code, "invalid_dedupe_key")
        self.assertIsInstance(ctx.exception.__cause__, KeyError)
        self.assertNotIn(SENTINEL, str(ctx.exception))

    def test_serialization_failure_is_payload_error(self) -> None:
        with self.assertRaises(NoticePayloadError) as ctx:
            emit_notice(
                "test.serializer", {"name": "member-name"}, organization=self.org
            )
        exc = ctx.exception
        self.assertEqual(exc.errors, [{"loc": (), "type": "serialization_failed"}])
        self.assertIsNotNone(exc.__cause__)
        self.assertNotIn(SENTINEL, str(exc))
        self.assertNotIn("member-name", str(exc))

    def test_unvalidated_instance_is_revalidated(self) -> None:
        with self.assertRaises(NoticePayloadError) as ctx:
            emit_notice(
                "test.alert",
                AlertPayload.model_construct(member_id="x", reason="r"),
                organization=self.org,
            )
        self.assertEqual(
            ctx.exception.errors, [{"loc": ("member_id",), "type": "int_parsing"}]
        )
        mutated = AlertPayload(member_id=1, reason="r")
        mutated.member_id = "y"  # type: ignore[assignment]
        with self.assertRaises(NoticePayloadError):
            emit_notice("test.alert", mutated, organization=self.org)
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_subclass_instance_drops_extra_fields(self) -> None:
        class WiderPayload(AlertPayload):
            secret: str

        notice = emit_notice(
            "test.alert",
            WiderPayload(member_id=2, reason="r", secret="s"),
            organization=self.org,
        )
        assert notice is not None
        self.assertEqual(notice.payload, {"member_id": 2, "reason": "r"})

    def test_wrong_model_instance_is_invalid_payload(self) -> None:
        with self.assertRaises(NoticePayloadError) as ctx:
            emit_notice(
                "test.alert",
                StampPayload(at=datetime.now(UTC), ref=uuid.uuid4()),
                organization=self.org,
            )
        self.assertEqual(ctx.exception.code, "invalid_payload")


@override_settings(OPS_NOTICES_STRICT=False)
class LenientFailureTests(FailureTriggers):
    def test_each_failure_returns_none_and_keeps_outer_transaction(self) -> None:
        for index, (code, trigger) in enumerate(self._triggers()):
            with self.subTest(index=index, code=code):
                sentinel_name = f"Sentinel {index} {code}"
                with capture_logs() as logs, transaction.atomic():
                    Organization.objects.create(name=sentinel_name, owner=self.admin)
                    self.assertIsNone(trigger())
                self.assertEqual(OpsNotice.objects.count(), 0)
                self.assertTrue(
                    Organization.objects.filter(name=sentinel_name).exists()
                )
                failed = self._failed_logs(logs)
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]["code"], code)
                self.assertEqual(failed[0]["log_level"], "error")
                self.assertEqual(failed[0]["system"], "opsnotices")
                self.assertEqual(failed[0]["subsystem"], "emit")
                self.assertNotIn(SENTINEL, repr(logs))

    def test_payload_failure_log_fields(self) -> None:
        with capture_logs() as logs:
            emit_notice("test.alert", {"member_id": "x"}, organization=self.org)
        (entry,) = self._failed_logs(logs)
        self.assertEqual(entry["error_count"], 2)
        self.assertEqual(entry["notice_key"], "test.alert")
        self.assertEqual(entry["organization_id"], self.org.id)
        self.assertIn(entry["first_error_loc"], {"member_id", "reason"})
        self.assertTrue(entry["first_error_type"])
        self.assertNotIn("error_type", entry)

    def test_chained_cause_type_is_logged(self) -> None:
        with (
            patch.object(OpsNotice.objects, "create", side_effect=DatabaseError("x")),
            capture_logs() as logs,
        ):
            emit_notice("test.alert", _alert(), organization=self.org)
        with capture_logs() as hook_logs:
            emit_notice("test.badhook", _alert(), organization=self.org)
        (db_entry,) = self._failed_logs(logs)
        (hook_entry,) = self._failed_logs(hook_logs)
        self.assertEqual(db_entry["code"], "database_error")
        self.assertEqual(db_entry["error_type"], "DatabaseError")
        self.assertEqual(hook_entry["code"], "invalid_dedupe_key")
        self.assertEqual(hook_entry["error_type"], "KeyError")
        self.assertNotIn(SENTINEL, repr(hook_logs))


class ValidatorLeakTests(EmitTestBase):
    def test_validator_message_never_leaks(self) -> None:
        payload = {"name": "member-name"}
        with capture_logs() as logs, self.assertRaises(NoticePayloadError) as ctx:
            emit_notice("test.sentinel", payload, organization=self.org)
        exc = ctx.exception
        self.assertNotIn(SENTINEL, repr(exc.errors))
        self.assertNotIn(SENTINEL, str(exc))
        self.assertNotIn("member-name", str(exc))
        self.assertNotIn(SENTINEL, repr(logs))

        with (
            override_settings(OPS_NOTICES_STRICT=False),
            capture_logs() as lenient_logs,
        ):
            self.assertIsNone(
                emit_notice("test.sentinel", payload, organization=self.org)
            )
        self.assertEqual(len(self._failed_logs(lenient_logs)), 1)
        self.assertNotIn(SENTINEL, repr(lenient_logs))
        self.assertNotIn("member-name", repr(lenient_logs))


class CeleryGuardTests(EmitTestBase):
    def test_celery_guard_raises_without_database(self) -> None:
        cases: list[dict[str, Any]] = [
            {},
            {"default": {"ENGINE": "django.db.backends.dummy"}},
        ]
        for databases in cases:
            with self.subTest(databases=databases):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with (
                        override_settings(DATABASES=databases),
                        self.assertRaises(RuntimeError) as ctx,
                    ):
                        emit_notice("test.nope", {}, organization=self.org)
                self.assertIn("emit_ops_notice", str(ctx.exception))


class CeleryGuardSubprocessTests(SimpleTestCase):
    def test_celery_guard_fires_under_settings_celery(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import django\n"
            "django.setup()\n"
            "from django.db import connections\n"
            "connections['default'].settings_dict\n"
            "from opsnotices.services import emit_notice\n"
            "try:\n"
            "    emit_notice('test.nope', {}, organization=None)\n"
            "except RuntimeError as exc:\n"
            "    if 'emit_ops_notice' in str(exc):\n"
            "        print('GUARD_OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("GUARD_OK", result.stdout)


class DedupeTests(EmitTestBase):
    def test_same_identity_dedupes(self) -> None:
        first = emit_notice("test.alert", _alert(reason="one"), organization=self.org)
        assert first is not None
        first_seen = first.last_seen_at
        OpsNotice.objects.filter(pk=first.pk).update(
            delivery_state=OpsNotice.DeliveryState.SENT
        )
        second = emit_notice(
            "test.alert", _alert(reason="two"), organization=self.org, actor=self.user
        )
        assert second is not None
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(OpsNotice.objects.count(), 1)
        self.assertEqual(second.occurrences, 2)
        self.assertGreater(second.last_seen_at, first_seen)
        self.assertEqual(second.payload, _alert(reason="two"))
        self.assertEqual(second.actor_id, self.user.id)
        self.assertEqual(second.delivery_state, OpsNotice.DeliveryState.SENT)

    def test_new_notice_delivery_pending(self) -> None:
        notice = emit_notice("test.alert", _alert(), organization=self.org)
        assert notice is not None
        notice.refresh_from_db()
        self.assertEqual(notice.delivery_state, OpsNotice.DeliveryState.PENDING)
        self.assertEqual(notice.dedupe_key, "member:1")
        self.assertEqual(notice.category, "urgent")
        self.assertEqual(notice.severity, "warning")
        self.assertEqual(notice.occurrences, 1)

    def test_explicit_dedupe_overrides_hook(self) -> None:
        a = emit_notice(
            "test.alert", _alert(member_id=1), organization=self.org, dedupe_key="x"
        )
        b = emit_notice(
            "test.alert", _alert(member_id=2), organization=self.org, dedupe_key="x"
        )
        assert a is not None and b is not None
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(b.dedupe_key, "x")
        c = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, dedupe_key="y"
        )
        d = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, dedupe_key="y"
        )
        assert c is not None and d is not None
        self.assertEqual(c.pk, d.pk)

    def test_empty_dedupe_creates_new_rows(self) -> None:
        emit_notice("test.nodedupe", _alert(), organization=self.org)
        emit_notice("test.nodedupe", _alert(), organization=self.org)
        emit_notice("test.alert", _alert(), organization=self.org, dedupe_key="")
        emit_notice("test.alert", _alert(), organization=self.org, dedupe_key="")
        self.assertEqual(OpsNotice.objects.count(), 4)
        self.assertEqual(
            set(OpsNotice.objects.values_list("dedupe_key", flat=True)), {""}
        )

    def test_reemit_after_resolve_creates_new_row(self) -> None:
        first = emit_notice("test.alert", _alert(), organization=self.org)
        assert first is not None
        OpsNotice.objects.filter(pk=first.pk).update(
            state=OpsNotice.State.RESOLVED, closed_at=timezone.now()
        )
        second = emit_notice("test.alert", _alert(), organization=self.org)
        assert second is not None
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(second.occurrences, 1)
        self.assertEqual(OpsNotice.objects.count(), 2)

    def test_dedupe_scoped_by_organization(self) -> None:
        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        emit_notice("test.alert", _alert(), organization=self.org)
        emit_notice("test.alert", _alert(), organization=other_org)
        self.assertEqual(OpsNotice.objects.count(), 2)

    def test_severity_escalates_never_downgrades(self) -> None:
        emit_notice("test.alert", _alert(), organization=self.org)
        notice = emit_notice(
            "test.alert", _alert(), organization=self.org, severity="critical"
        )
        assert notice is not None
        self.assertEqual(notice.severity, "critical")
        notice = emit_notice(
            "test.alert", _alert(), organization=self.org, severity=NoticeSeverity.INFO
        )
        assert notice is not None
        self.assertEqual(notice.severity, "critical")
        self.assertEqual(notice.occurrences, 3)

    def test_explicit_severity_on_create(self) -> None:
        notice = emit_notice(
            "test.chore", _alert(), organization=self.org, severity="critical"
        )
        assert notice is not None
        self.assertEqual(notice.severity, "critical")

    def test_dedupe_key_length_boundary(self) -> None:
        ok = emit_notice(
            "test.alert",
            _alert(),
            organization=self.org,
            dedupe_key="k" * DEDUPE_KEY_MAX,
        )
        assert ok is not None
        self.assertEqual(len(ok.dedupe_key), 200)
        with self.assertRaises(NoticeEmitError) as ctx:
            emit_notice(
                "test.alert", _alert(), organization=self.org, dedupe_key="k" * 201
            )
        self.assertEqual(ctx.exception.code, "dedupe_key_too_long")
        self.assertEqual(OpsNotice.objects.count(), 1)

    def test_payload_with_datetime_and_uuid_round_trips(self) -> None:
        at = datetime(2026, 11, 17, 12, 30, tzinfo=UTC)
        ref = uuid.uuid4()
        notice = emit_notice(
            "test.stamp", StampPayload(at=at, ref=ref), organization=self.org
        )
        assert notice is not None
        notice.refresh_from_db()
        self.assertIsInstance(notice.payload["at"], str)
        self.assertEqual(notice.payload["ref"], str(ref))
        restored = StampPayload.model_validate(notice.payload)
        self.assertEqual(restored.at, at)
        self.assertEqual(restored.ref, ref)

    def test_model_instance_payload_accepted(self) -> None:
        notice = emit_notice(
            "test.alert", AlertPayload(member_id=4, reason="r"), organization=self.org
        )
        assert notice is not None
        self.assertEqual(notice.payload, {"member_id": 4, "reason": "r"})
        self.assertEqual(notice.dedupe_key, "member:4")


class EventIdentityTests(EmitTestBase):
    def test_event_identity(self) -> None:
        event_b = self._event("Event B")
        a = emit_notice("test.alert", _alert(), organization=self.org, event=self.event)
        b = emit_notice("test.alert", _alert(), organization=self.org, event=event_b)
        assert a is not None and b is not None
        self.assertNotEqual(a.pk, b.pk)
        a.refresh_from_db()
        self.assertEqual(a.event_id, self.event.id)
        self.assertEqual(a.event_key, self.event.id)
        self.assertEqual(a.event_name, "Test Event")

        none = emit_notice("test.alert", _alert(), organization=self.org)
        assert none is not None
        self.assertEqual(none.event_key, 0)
        self.assertIsNone(none.event_id)
        self.assertIsNone(none.event_repeater_id)
        self.assertEqual(none.event_name, "")

        gone = emit_notice(
            "test.alert",
            _alert(),
            organization=self.org,
            event=EventRef(id=999, name="Gone", event_repeater_id=7),
        )
        assert gone is not None
        gone.refresh_from_db()
        self.assertIsNone(gone.event_id)
        self.assertEqual(gone.event_key, 999)
        self.assertEqual(gone.event_name, "Gone")
        self.assertEqual(gone.event_repeater_id, 7)
        self.assertEqual(OpsNotice.objects.count(), 4)

        self.event.name = "Renamed Event"
        self.event.save(update_fields=["name"])
        again = emit_notice(
            "test.alert", _alert(), organization=self.org, event=self.event
        )
        assert again is not None
        self.assertEqual(again.pk, a.pk)
        self.assertEqual(again.event_name, "Renamed Event")
        self.assertEqual(again.event_key, self.event.id)
        self.assertEqual(OpsNotice.objects.count(), 4)

    def test_event_ref_reemit_refreshes_snapshot(self) -> None:
        first = emit_notice(
            "test.alert",
            _alert(),
            organization=self.org,
            event=EventRef(id=999, name="Old", event_repeater_id=7),
        )
        again = emit_notice(
            "test.alert",
            _alert(),
            organization=self.org,
            event=EventRef(id=999, name="New", event_repeater_id=8),
        )
        assert first is not None and again is not None
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(again.event_name, "New")
        self.assertEqual(again.event_repeater_id, 8)
        self.assertEqual(again.event_key, 999)
        self.assertIsNone(again.event_id)

    def test_event_repeater_id_snapshot(self) -> None:
        repeater = self._repeater()
        series_event = self._event("Series")
        series_event.event_repeater = repeater
        series_event.save(update_fields=["event_repeater"])
        series = emit_notice(
            "test.alert", _alert(), organization=self.org, event=series_event
        )
        one_off = emit_notice(
            "test.alert", _alert(), organization=self.org, event=self.event
        )
        assert series is not None and one_off is not None
        series.refresh_from_db()
        one_off.refresh_from_db()
        self.assertEqual(series.event_repeater_id, series_event.event_repeater_id)
        self.assertEqual(series.event_repeater_id, repeater.id)
        self.assertIsNone(one_off.event_repeater_id)


class IdempotencyTests(EmitTestBase):
    def test_emit_id_idempotent(self) -> None:
        emit_id = uuid.uuid4()
        first = emit_notice(
            "test.alert", _alert(), organization=self.org, emit_id=emit_id
        )
        second = emit_notice(
            "test.alert", _alert(), organization=self.org, emit_id=emit_id
        )
        assert first is not None and second is not None
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.occurrences, 1)
        self.assertEqual(second.last_emit_id, emit_id)
        self.assertEqual(OpsNotice.objects.count(), 1)

    def test_emit_id_idempotent_without_dedupe(self) -> None:
        emit_id = uuid.uuid4()
        first = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, emit_id=emit_id
        )
        second = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, emit_id=emit_id
        )
        assert first is not None and second is not None
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(OpsNotice.objects.count(), 1)

    def test_emit_without_id_keeps_earlier_emit_id(self) -> None:
        emit_id = uuid.uuid4()
        emit_notice("test.alert", _alert(), organization=self.org, emit_id=emit_id)
        bumped = emit_notice("test.alert", _alert(), organization=self.org)
        assert bumped is not None
        self.assertEqual(bumped.occurrences, 2)
        self.assertEqual(bumped.last_emit_id, emit_id)
        with capture_logs() as logs:
            replay = emit_notice(
                "test.alert", _alert(), organization=self.org, emit_id=emit_id
            )
        assert replay is not None
        self.assertEqual(replay.pk, bumped.pk)
        self.assertEqual(replay.occurrences, 2)
        self.assertFalse(
            [
                e
                for e in logs
                if e["event"] in {"ops_notice_emitted", "ops_notice_repeated"}
            ]
        )

    def test_new_emit_id_bumps_and_records(self) -> None:
        emit_notice("test.alert", _alert(), organization=self.org, emit_id=uuid.uuid4())
        later = uuid.uuid4()
        notice = emit_notice(
            "test.alert", _alert(), organization=self.org, emit_id=later
        )
        assert notice is not None
        self.assertEqual(notice.occurrences, 2)
        self.assertEqual(notice.last_emit_id, later)

    def test_shared_emit_id_across_keys_creates_each(self) -> None:
        emit_id = uuid.uuid4()
        alert = emit_notice(
            "test.alert", _alert(), organization=self.org, emit_id=emit_id
        )
        chore = emit_notice(
            "test.chore", _alert(), organization=self.org, emit_id=emit_id
        )
        nodedupe = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, emit_id=emit_id
        )
        assert alert is not None and chore is not None and nodedupe is not None
        self.assertEqual(len({alert.pk, chore.pk, nodedupe.pk}), 3)
        self.assertEqual(OpsNotice.objects.count(), 3)

    def test_shared_emit_id_across_dedupe_keys_creates_each(self) -> None:
        emit_id = uuid.uuid4()
        first = emit_notice(
            "test.alert", _alert(member_id=1), organization=self.org, emit_id=emit_id
        )
        second = emit_notice(
            "test.alert", _alert(member_id=2), organization=self.org, emit_id=emit_id
        )
        assert first is not None and second is not None
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(OpsNotice.objects.count(), 2)

    def test_shared_emit_id_across_events_creates_each(self) -> None:
        emit_id = uuid.uuid4()
        other = self._event("Other")
        first = emit_notice(
            "test.alert",
            _alert(),
            organization=self.org,
            event=self.event,
            emit_id=emit_id,
        )
        second = emit_notice(
            "test.alert", _alert(), organization=self.org, event=other, emit_id=emit_id
        )
        assert first is not None and second is not None
        self.assertNotEqual(first.pk, second.pk)

    def test_concurrent_replay_without_dedupe_returns_existing(self) -> None:
        emit_id = uuid.uuid4()
        first = emit_notice(
            "test.nodedupe", _alert(), organization=self.org, emit_id=emit_id
        )
        assert first is not None
        real = services._find_replay
        calls: list[int] = []

        def miss_first(*args: Any) -> OpsNotice | None:
            calls.append(1)
            return None if len(calls) == 1 else real(*args)

        with (
            patch("opsnotices.services._find_replay", side_effect=miss_first),
            transaction.atomic(),
        ):
            Organization.objects.create(name="Sentinel replay", owner=self.admin)
            replay = emit_notice(
                "test.nodedupe", _alert(), organization=self.org, emit_id=emit_id
            )
        self.assertEqual(len(calls), 2)
        assert replay is not None
        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(OpsNotice.objects.count(), 1)
        self.assertTrue(Organization.objects.filter(name="Sentinel replay").exists())


class ResolveRaceTests(EmitTestBase):
    def test_bump_skips_notice_resolved_mid_emit(self) -> None:
        original = emit_notice("test.alert", _alert(), organization=self.org)
        assert original is not None
        real = services._find_open_notice

        def resolve_then_return(
            organization_id: int, key: str, event_key: int, dedupe_key: str
        ) -> OpsNotice | None:
            found = real(organization_id, key, event_key, dedupe_key)
            if found is not None:
                OpsNotice.objects.filter(pk=found.pk).update(
                    state=OpsNotice.State.RESOLVED, closed_at=timezone.now()
                )
            return found

        with patch(
            "opsnotices.services._find_open_notice", side_effect=resolve_then_return
        ):
            notice = emit_notice(
                "test.alert", _alert(reason="again"), organization=self.org
            )
        assert notice is not None
        self.assertNotEqual(notice.pk, original.pk)
        self.assertIsNone(notice.closed_at)
        self.assertEqual(notice.occurrences, 1)
        original.refresh_from_db()
        self.assertEqual(original.occurrences, 1)
        self.assertEqual(original.payload, _alert())
        self.assertEqual(original.state, OpsNotice.State.RESOLVED)


@contextmanager
def _miss_first_lookup() -> Iterator[list[int]]:
    real = services._find_open_notice
    calls: list[int] = []

    def wrapper(
        organization_id: int, key: str, event_key: int, dedupe_key: str
    ) -> OpsNotice | None:
        calls.append(1)
        if len(calls) == 1:
            return None
        return real(organization_id, key, event_key, dedupe_key)

    with patch("opsnotices.services._find_open_notice", side_effect=wrapper):
        yield calls


class IntegrityRetryTests(EmitTestBase):
    def test_integrity_error_retry_updates(self) -> None:
        competitor = OpsNotice.objects.create(
            organization=self.org,
            key="test.alert",
            category="urgent",
            severity="warning",
            dedupe_key="member:1",
            payload=_alert(),
        )
        with _miss_first_lookup() as calls, transaction.atomic():
            Organization.objects.create(name="Sentinel retry", owner=self.admin)
            notice = emit_notice(
                "test.alert", _alert(reason="again"), organization=self.org
            )
        self.assertEqual(len(calls), 2)
        assert notice is not None
        self.assertEqual(notice.pk, competitor.pk)
        self.assertEqual(notice.occurrences, 2)
        self.assertEqual(notice.payload, _alert(reason="again"))
        self.assertEqual(OpsNotice.objects.count(), 1)
        self.assertTrue(Organization.objects.filter(name="Sentinel retry").exists())

    def test_integrity_error_retry_miss_event_conflict(self) -> None:
        error = IntegrityError("NOT NULL constraint failed")
        with (
            patch.object(OpsNotice.objects, "create", side_effect=error),
            self.assertRaises(NoticeEmitError) as ctx,
        ):
            emit_notice("test.alert", _alert(), organization=self.org)
        self.assertEqual(ctx.exception.code, "event_conflict")
        self.assertIs(ctx.exception.__cause__, error)

        with (
            override_settings(OPS_NOTICES_STRICT=False),
            patch.object(OpsNotice.objects, "create", side_effect=IntegrityError),
            capture_logs() as logs,
            transaction.atomic(),
        ):
            Organization.objects.create(name="Sentinel conflict", owner=self.admin)
            self.assertIsNone(
                emit_notice("test.alert", _alert(), organization=self.org)
            )
        (entry,) = self._failed_logs(logs)
        self.assertEqual(entry["code"], "event_conflict")
        self.assertEqual(entry["error_type"], "IntegrityError")
        self.assertEqual(OpsNotice.objects.count(), 0)
        self.assertTrue(Organization.objects.filter(name="Sentinel conflict").exists())


class EmitLogTests(EmitTestBase):
    def test_emitted_and_repeated_logs(self) -> None:
        with capture_logs() as logs:
            notice = emit_notice(
                "test.alert", _alert(), organization=self.org, event=self.event
            )
            emit_notice("test.alert", _alert(), organization=self.org, event=self.event)
        assert notice is not None
        emitted = [e for e in logs if e["event"] == "ops_notice_emitted"]
        repeated = [e for e in logs if e["event"] == "ops_notice_repeated"]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["log_level"], "info")
        self.assertEqual(emitted[0]["notice_id"], notice.pk)
        self.assertEqual(emitted[0]["notice_key"], "test.alert")
        self.assertEqual(emitted[0]["category"], "urgent")
        self.assertEqual(emitted[0]["severity"], "warning")
        self.assertEqual(emitted[0]["organization_id"], self.org.id)
        self.assertEqual(emitted[0]["event_id"], self.event.id)
        self.assertTrue(emitted[0]["dedupe"])
        self.assertEqual(len(repeated), 1)
        self.assertEqual(repeated[0]["log_level"], "debug")
        self.assertEqual(repeated[0]["occurrences"], 2)
        for entry in emitted + repeated:
            self.assertEqual(entry["system"], "opsnotices")
            self.assertEqual(entry["subsystem"], "emit")
        self.assertNotIn("late", repr(logs))
