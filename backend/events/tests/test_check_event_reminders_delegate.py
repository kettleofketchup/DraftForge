"""check_event_reminders is now a thin wrapper around fire_due_reminders."""

from unittest.mock import patch

from django.test import TestCase

from events.tasks import check_event_reminders


class CheckEventRemindersDelegateTest(TestCase):
    @patch("events.tasks.fire_due_reminders")
    def test_delegates_to_fire_due_reminders(self, mock_fire):
        mock_fire.return_value = "ok"
        result = check_event_reminders()
        mock_fire.assert_called_once()
        self.assertEqual(result, "ok")

    def test_task_has_acks_late_and_reject_on_worker_lost(self):
        # Celery exposes options on the task instance
        self.assertTrue(check_event_reminders.acks_late)
        self.assertTrue(check_event_reminders.reject_on_worker_lost)
