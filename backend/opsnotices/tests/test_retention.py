from datetime import timedelta
from typing import Any

from django.utils import timezone

from app.models import Organization
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.retention import RETENTION
from opsnotices.services import (
    RETENTION_MIN,
    emit_notice,
    purge_notices,
    resolve_notice_by_id,
)
from opsnotices.tests.types import register_test_types

YEAR: timedelta = timedelta(days=365)


class RetentionTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.old = timezone.now() - YEAR - timedelta(days=10)
        self.recent = timezone.now() - timedelta(days=30)

    def _emit(
        self,
        key: str,
        member_id: int,
        organization: Organization | None = None,
    ) -> OpsNotice:
        payload: dict[str, Any] = {"member_id": member_id, "reason": "late"}
        notice = emit_notice(key, payload, organization=organization or self.org)
        assert notice is not None
        return notice

    def _close(self, notice: OpsNotice) -> None:
        closed = resolve_notice_by_id(notice, reason="done", closed_by=None)
        assert closed is not None

    def _backdate(self, notice: OpsNotice, **fields: Any) -> None:
        OpsNotice.objects.filter(pk=notice.pk).update(**fields)

    def _exists(self, notice: OpsNotice) -> bool:
        return OpsNotice.objects.filter(pk=notice.pk).exists()

    def test_purges_closed_past_cutoff(self) -> None:
        old_closed = self._emit("test.alert", 1)
        self._close(old_closed)
        self._backdate(old_closed, closed_at=self.old, last_seen_at=self.old)
        recent_closed = self._emit("test.alert", 2)
        self._close(recent_closed)
        self._backdate(recent_closed, closed_at=self.recent, last_seen_at=self.old)

        deleted = purge_notices(older_than=YEAR)

        self.assertEqual(deleted, 1)
        self.assertFalse(self._exists(old_closed))
        self.assertTrue(self._exists(recent_closed))

    def test_purges_log_rows_by_last_seen_even_open(self) -> None:
        old_log = self._emit("test.log", 1)
        self._backdate(old_log, last_seen_at=self.old)
        recent_log = self._emit("test.log", 2)
        self._backdate(recent_log, last_seen_at=self.recent)

        deleted = purge_notices(older_than=YEAR)

        self.assertEqual(deleted, 1)
        self.assertFalse(self._exists(old_log))
        self.assertTrue(self._exists(recent_log))
        recent_log.refresh_from_db()
        self.assertEqual(recent_log.state, OpsNotice.State.OPEN)

    def test_keeps_open_urgent_and_task_and_recent(self) -> None:
        open_urgent = self._emit("test.alert", 1)
        self._backdate(open_urgent, last_seen_at=self.old)
        open_task = self._emit("test.chore", 2)
        self._backdate(open_task, last_seen_at=self.old)
        recent_closed = self._emit("test.alert", 3)
        self._close(recent_closed)
        self._backdate(recent_closed, closed_at=self.recent)

        deleted = purge_notices(older_than=YEAR)

        self.assertEqual(deleted, 0)
        for notice in (open_urgent, open_task, recent_closed):
            self.assertTrue(self._exists(notice))

    def test_scoped_to_organization(self) -> None:
        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        mine = self._emit("test.log", 1)
        theirs = self._emit("test.log", 1, organization=other_org)
        self._backdate(mine, last_seen_at=self.old)
        self._backdate(theirs, last_seen_at=self.old)

        deleted = purge_notices(older_than=YEAR, organization=self.org)

        self.assertEqual(deleted, 1)
        self.assertFalse(self._exists(mine))
        self.assertTrue(self._exists(theirs))

    def test_older_than_below_365_days_raises(self) -> None:
        notice = self._emit("test.log", 1)
        self._backdate(notice, last_seen_at=self.old)

        with self.assertRaises(ValueError):
            purge_notices(older_than=YEAR - timedelta(seconds=1))

        self.assertTrue(self._exists(notice))
        self.assertEqual(purge_notices(older_than=RETENTION_MIN), 1)

    def test_declaration_points_at_real_purge(self) -> None:
        self.assertIs(RETENTION.purge, purge_notices)
        self.assertEqual(RETENTION.minimum, RETENTION_MIN)
        self.assertEqual(RETENTION_MIN, timedelta(days=365))
        self.assertEqual(RETENTION.model_label, "opsnotices.OpsNotice")
        self.assertEqual(RETENTION.timestamp_fields, ("closed_at", "last_seen_at"))
        self.assertEqual(RETENTION.open_rows_kept, "urgent/task")
