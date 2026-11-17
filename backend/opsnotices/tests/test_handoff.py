import uuid
from typing import Any

from django.db import connection, transaction
from structlog.testing import capture_logs

from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.services import _HandOff, emit_notice
from opsnotices.signals import notice_emitted
from opsnotices.tests.types import register_test_types


def _alert(member_id: int = 1, reason: str = "late") -> dict[str, Any]:
    return {"member_id": member_id, "reason": reason}


class _Boom(Exception):
    pass


class HandOffTestBase(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.calls: list[dict[str, Any]] = []
        notice_emitted.connect(self._receiver, weak=False)
        self.addCleanup(notice_emitted.disconnect, self._receiver)

    def _receiver(self, sender: type[OpsNotice], **kwargs: Any) -> None:
        self.calls.append({"sender": sender, **kwargs})

    def _emit(self, **kwargs: Any) -> OpsNotice | None:
        return emit_notice("test.alert", _alert(), organization=self.org, **kwargs)


class HandOffTests(HandOffTestBase):
    def test_receiver_called_once_after_commit_with_created(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            notice = self._emit()
            self.assertEqual(self.calls, [])
        assert notice is not None
        self.assertEqual(
            self.calls,
            [
                {
                    "sender": OpsNotice,
                    "signal": notice_emitted,
                    "notice_id": notice.pk,
                    "created": True,
                    "occurrences": 1,
                }
            ],
        )

    def test_reemit_handoff_created_false(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self._emit()
        with self.captureOnCommitCallbacks(execute=True):
            notice = self._emit()
        assert notice is not None
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.calls[1]["created"])
        self.assertEqual(self.calls[1]["occurrences"], 2)
        self.assertEqual(self.calls[1]["notice_id"], notice.pk)

    def test_three_emits_one_transaction_one_handoff(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                notice = self._emit()
                self._emit()
                self._emit()
        assert notice is not None
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["notice_id"], notice.pk)
        self.assertTrue(self.calls[0]["created"])
        self.assertEqual(self.calls[0]["occurrences"], 3)

    def test_rolled_back_savepoint_then_outer_emit_one_handoff(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                try:
                    with transaction.atomic():
                        self._emit()
                        raise _Boom
                except _Boom:
                    pass
                notice = self._emit()
        assert notice is not None
        self.assertEqual(OpsNotice.objects.count(), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["notice_id"], notice.pk)
        self.assertTrue(self.calls[0]["created"])
        self.assertEqual(self.calls[0]["occurrences"], 1)

    def test_failing_receiver_logged_and_emit_returns(self) -> None:
        def broken(sender: type[OpsNotice], **kwargs: Any) -> None:
            raise _Boom("receiver failed")

        notice_emitted.connect(broken, weak=False)
        self.addCleanup(notice_emitted.disconnect, broken)
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                notice = self._emit()
        self.assertIsNotNone(notice)
        assert notice is not None
        self.assertEqual(len(self.calls), 1)
        failures = [
            entry
            for entry in logs
            if entry["event"] == "ops_notice_handoff_receiver_failed"
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["notice_id"], notice.pk)
        self.assertEqual(failures[0]["log_level"], "error")
        self.assertIn("broken", failures[0]["receiver"])
        self.assertIsInstance(failures[0]["exc_info"], _Boom)

    def test_run_on_commit_shape_pinned(self) -> None:
        with transaction.atomic():
            before = len(connection.run_on_commit)
            notice = self._emit()
            added = connection.run_on_commit[before:]
        assert notice is not None
        self.assertEqual(len(added), 1)
        entry = added[0]
        self.assertIsInstance(entry, tuple)
        self.assertEqual(len(entry), 3)
        sids, func, robust = entry
        self.assertIsInstance(sids, set)
        self.assertIsInstance(func, _HandOff)
        self.assertEqual(func.notice_id, notice.pk)
        self.assertTrue(func.created)
        self.assertIsInstance(robust, bool)

    def test_idempotent_replay_no_second_handoff(self) -> None:
        emit_id = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            first = self._emit(emit_id=emit_id)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            second = self._emit(emit_id=emit_id)
        assert first is not None and second is not None
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(callbacks, [])
        self.assertEqual(len(self.calls), 1)

    def test_outer_rollback_discards_notice_and_handoff(self) -> None:
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(_Boom):
                with transaction.atomic():
                    notice = self._emit()
                    self.assertIsNotNone(notice)
                    raise _Boom
        self.assertEqual(OpsNotice.objects.count(), 0)
        self.assertEqual(callbacks, [])
        self.assertEqual(self.calls, [])

    def test_handoff_skips_deleted_notice(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                notice = self._emit()
                assert notice is not None
                notice.delete()
        self.assertEqual(self.calls, [])
