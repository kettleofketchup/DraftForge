from datetime import time
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from events.models import EventRepeater
from events.tests.base import EventTestCase
from opsnotices.models import OPEN_STATES, OpsNotice


class OpsNoticeModelTests(EventTestCase):
    def _notice(self, **overrides: object) -> OpsNotice:
        fields: dict[str, object] = {
            "organization": self.org,
            "key": "test.thing",
            "category": "log",
            "severity": "info",
            "dedupe_key": "d1",
        }
        fields.update(overrides)
        return OpsNotice.objects.create(**fields)

    def test_open_dedupe_unique_blocks_second_open_row(self) -> None:
        self._notice()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._notice()

    def test_unique_ignores_empty_dedupe_and_closed_rows(self) -> None:
        self._notice(dedupe_key="")
        self._notice(dedupe_key="")
        self._notice(state=OpsNotice.State.RESOLVED, closed_at=timezone.now())
        self._notice(state=OpsNotice.State.RESOLVED, closed_at=timezone.now())
        self._notice()
        self.assertEqual(OpsNotice.objects.count(), 5)

    def test_unique_scoped_by_event_key(self) -> None:
        self._notice(event_key=5)
        self._notice(event_key=0)
        self.assertEqual(OpsNotice.objects.count(), 2)

    def test_emit_id_unique_per_notice_identity(self) -> None:
        emit_id = uuid4()
        self._notice(dedupe_key="", last_emit_id=emit_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._notice(dedupe_key="", last_emit_id=emit_id)
        self._notice(key="test.other", dedupe_key="", last_emit_id=emit_id)
        self._notice(dedupe_key="d2", last_emit_id=emit_id)
        self._notice(dedupe_key="", event_key=7, last_emit_id=emit_id)
        self._notice(dedupe_key="", last_emit_id=None)
        self._notice(dedupe_key="", last_emit_id=None)
        self.assertEqual(OpsNotice.objects.count(), 6)

    def test_occurrences_check_constraint(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._notice(occurrences=0)

    def test_state_closed_at_consistency(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._notice(state=OpsNotice.State.OPEN, closed_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._notice(state=OpsNotice.State.RESOLVED, closed_at=None)

    def test_event_delete_sets_null_keeps_snapshot(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency="weekly",
            time_of_day=time(19, 0),
            starts_at=timezone.now().date(),
        )
        self.event.event_repeater = repeater
        self.event.save(update_fields=["event_repeater"])
        event_id = self.event.id
        notice = self._notice(
            event=self.event,
            event_key=event_id,
            event_name=self.event.name,
            event_repeater_id=repeater.id,
        )
        self._notice()

        self.event.delete()

        notice.refresh_from_db()
        self.assertIsNone(notice.event_id)
        self.assertEqual(notice.event_key, event_id)
        self.assertEqual(notice.event_name, "Test Event")
        self.assertEqual(notice.event_repeater_id, repeater.id)

    def test_defaults(self) -> None:
        notice = OpsNotice.objects.create(
            organization=self.org, key="test.thing", category="log", severity="info"
        )
        notice.refresh_from_db()
        self.assertEqual(notice.state, OpsNotice.State.OPEN)
        self.assertEqual(notice.delivery_state, OpsNotice.DeliveryState.PENDING)
        self.assertEqual(notice.occurrences, 1)
        self.assertEqual(notice.event_key, 0)
        self.assertEqual(notice.payload, {})
        self.assertEqual(notice.dedupe_key, "")
        self.assertIsNone(notice.event_repeater_id)
        self.assertIsNone(notice.closed_at)
        self.assertIsNone(notice.last_emit_id)
        self.assertEqual(str(notice), "test.thing (open)")
        self.assertEqual(OPEN_STATES, ("open",))
