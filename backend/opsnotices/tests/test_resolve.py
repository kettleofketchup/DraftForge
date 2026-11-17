import warnings
from typing import Any

from django.test import override_settings
from structlog.testing import capture_logs

from events.models import Event
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.services import (
    CLOSE_NOTE_MAX,
    EventRef,
    emit_notice,
    resolve_notice,
    resolve_notice_by_id,
)
from opsnotices.signals import notice_resolved
from opsnotices.tests.types import register_test_types


def _alert(member_id: int = 1, reason: str = "late") -> dict[str, Any]:
    return {"member_id": member_id, "reason": reason}


class ResolveTestBase(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.resolved: list[dict[str, Any]] = []
        notice_resolved.connect(self._receiver, weak=False)
        self.addCleanup(notice_resolved.disconnect, self._receiver)

    def _receiver(self, sender: type[OpsNotice], **kwargs: Any) -> None:
        self.resolved.append({"sender": sender, **kwargs})

    def _emit(
        self, key: str = "test.alert", event: Event | EventRef | None = None
    ) -> OpsNotice:
        notice = emit_notice(key, _alert(), organization=self.org, event=event)
        assert notice is not None
        return notice


class ResolveTests(ResolveTestBase):
    def test_resolve_by_identity_sets_closed_fields_and_signals(self) -> None:
        notice = self._emit(event=self.event)
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                result = resolve_notice(
                    "test.alert",
                    "member:1",
                    organization=self.org,
                    event=self.event,
                    reason="fixed",
                    closed_by=self.admin,
                )
                self.assertEqual(self.resolved, [])
        assert result is not None
        self.assertEqual(result.pk, notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.state, OpsNotice.State.RESOLVED)
        self.assertIsNotNone(notice.closed_at)
        self.assertEqual(notice.close_note, "fixed")
        self.assertEqual(notice.closed_by, self.admin)
        self.assertEqual(
            self.resolved,
            [{"sender": OpsNotice, "signal": notice_resolved, "notice_id": notice.pk}],
        )
        entries = [e for e in logs if e["event"] == "ops_notice_resolved"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["notice_id"], notice.pk)
        self.assertEqual(entries[0]["notice_key"], "test.alert")
        self.assertEqual(entries[0]["close_note"], "fixed")
        self.assertEqual(entries[0]["closed_by_id"], self.admin.pk)
        self.assertEqual(entries[0]["system"], "opsnotices")
        self.assertEqual(entries[0]["subsystem"], "emit")

    def test_resolve_matches_event_identity(self) -> None:
        event_notice = self._emit(event=self.event)
        orgwide = self._emit()
        result = resolve_notice(
            "test.alert", "member:1", organization=self.org, reason="done"
        )
        assert result is not None
        self.assertEqual(result.pk, orgwide.pk)
        event_notice.refresh_from_db()
        self.assertEqual(event_notice.state, OpsNotice.State.OPEN)

        ref_notice = self._emit(event=EventRef(id=999, name="Gone"))
        result = resolve_notice(
            "test.alert",
            "member:1",
            organization=self.org,
            event=EventRef(id=999, name="Gone"),
            reason="done",
        )
        assert result is not None
        self.assertEqual(result.pk, ref_notice.pk)

    def test_resolve_missing_returns_none_logs_debug(self) -> None:
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                result = resolve_notice(
                    "test.alert", "member:1", organization=self.org, reason="x"
                )
        self.assertIsNone(result)
        self.assertEqual(self.resolved, [])
        entries = [e for e in logs if e["event"] == "ops_notice_resolve_missing"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["log_level"], "debug")
        self.assertEqual(entries[0]["notice_key"], "test.alert")
        self.assertEqual(entries[0]["organization_id"], self.org.id)

    def test_resolve_skips_already_closed(self) -> None:
        notice = self._emit()
        resolve_notice_by_id(notice, reason="first", closed_by=None)
        self.assertIsNone(
            resolve_notice("test.alert", "member:1", organization=self.org, reason="x")
        )

    def test_resolve_empty_dedupe_raises_value_error(self) -> None:
        self._emit(key="test.nodedupe")
        with self.assertRaises(ValueError):
            resolve_notice("test.nodedupe", "", organization=self.org, reason="x")

    def test_resolve_by_id_idempotent(self) -> None:
        notice = self._emit()
        with self.captureOnCommitCallbacks(execute=True):
            first = resolve_notice_by_id(notice, reason="first", closed_by=self.admin)
        assert first is not None
        closed_at = first.closed_at
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                second = resolve_notice_by_id(notice, reason="second", closed_by=None)
        assert second is not None
        self.assertEqual(second.pk, notice.pk)
        self.assertEqual(second.close_note, "first")
        self.assertEqual(second.closed_by, self.admin)
        self.assertEqual(second.closed_at, closed_at)
        self.assertEqual(callbacks, [])
        self.assertEqual(len(self.resolved), 1)
        self.assertFalse([e for e in logs if e["event"] == "ops_notice_resolved"])

    def test_resolve_by_id_stale_instance_is_idempotent(self) -> None:
        notice = self._emit()
        stale = OpsNotice.objects.get(pk=notice.pk)
        resolve_notice_by_id(notice, reason="first", closed_by=self.admin)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            result = resolve_notice_by_id(stale, reason="second", closed_by=None)
        assert result is not None
        self.assertEqual(result.close_note, "first")
        self.assertEqual(result.state, OpsNotice.State.RESOLVED)
        self.assertEqual(callbacks, [])

    def test_resolve_by_id_deleted_row_returns_none(self) -> None:
        notice = self._emit()
        stale = OpsNotice.objects.get(pk=notice.pk)
        OpsNotice.objects.filter(pk=notice.pk).delete()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            result = resolve_notice_by_id(stale, reason="gone", closed_by=None)
        self.assertIsNone(result)
        self.assertEqual(callbacks, [])

    def test_close_note_required_and_max_200(self) -> None:
        notice = self._emit()
        for reason in ("", "   ", "x" * (CLOSE_NOTE_MAX + 1)):
            with self.subTest(reason=reason[:10], length=len(reason)):
                with self.assertRaises(ValueError):
                    resolve_notice_by_id(notice, reason=reason, closed_by=None)
                with self.assertRaises(ValueError):
                    resolve_notice(
                        "test.alert", "member:1", organization=self.org, reason=reason
                    )
        notice.refresh_from_db()
        self.assertEqual(notice.state, OpsNotice.State.OPEN)
        result = resolve_notice_by_id(
            notice, reason="x" * CLOSE_NOTE_MAX, closed_by=None
        )
        assert result is not None
        self.assertEqual(len(result.close_note), 200)

    def test_resolve_celery_guard(self) -> None:
        notice = self._emit()
        cases: list[dict[str, Any]] = [
            {},
            {"default": {"ENGINE": "django.db.backends.dummy"}},
        ]
        for databases in cases:
            with self.subTest(databases=databases):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with override_settings(DATABASES=databases):
                        with self.assertRaises(RuntimeError) as ctx:
                            resolve_notice(
                                "test.alert", "", organization=self.org, reason=""
                            )
                        self.assertIn("resolve_ops_notice", str(ctx.exception))
                        with self.assertRaises(RuntimeError):
                            resolve_notice_by_id(notice, reason="x", closed_by=None)
