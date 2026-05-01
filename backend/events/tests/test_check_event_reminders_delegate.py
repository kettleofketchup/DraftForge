"""check_event_reminders is now a thin wrapper around fire_due_reminders."""

from unittest.mock import patch

from django.test import TestCase

from events.tasks import check_event_reminders


class CheckEventRemindersDelegateTest(TestCase):
    @patch("events.scheduling.fire.fire_due_reminders")
    def test_delegates_to_fire_due_reminders(self, mock_fire):
        # Patch target is the SOURCE module (events.scheduling.fire). The new
        # check_event_reminders body does
        # `from events.scheduling.fire import fire_due_reminders` *inside*
        # the function, so the lookup happens at call time against the
        # source module's namespace. Patching events.tasks.fire_due_reminders
        # would not intercept it.
        mock_fire.return_value = "ok"
        result = check_event_reminders()
        mock_fire.assert_called_once()
        self.assertEqual(result, "ok")

    def test_task_has_acks_late_and_reject_on_worker_lost(self):
        # Celery exposes options on the task instance
        self.assertTrue(check_event_reminders.acks_late)
        self.assertTrue(check_event_reminders.reject_on_worker_lost)
