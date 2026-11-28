from importlib import import_module

from django.apps import apps
from django.db import connection

from events.models import Event
from org.tests.leadership_base import LeadershipTestCase

migration = import_module("events.migrations.0046_event_leadership_review_dm_dispatch")


class ReviewDMDispatchBackfillTest(LeadershipTestCase):
    def test_closed_and_reopened_events_are_fenced_but_future_events_are_not(
        self,
    ) -> None:
        self.run_snapshot()
        reopened, _ = self.make_event("Reopened")
        future, _ = self.make_event("Future")
        snap = self.snapshot(self.cap_a)
        snap.event = reopened
        snap.save(update_fields=["event"])
        Event.objects.update(leadership_review_dm_dispatch=None)
        migration.fence_existing_events(apps, connection.schema_editor())
        self.event.refresh_from_db()
        reopened.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(self.event.leadership_review_dm_dispatch, {})
        self.assertEqual(reopened.leadership_review_dm_dispatch, {})
        self.assertIsNone(future.leadership_review_dm_dispatch)
