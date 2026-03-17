from unittest.mock import patch

from events.models import EventState
from events.services import approve_signup, cancel_signup, confirm_signup, process_rsvp
from events.tests.base import EventTestCase


class ServiceDispatchTest(EventTestCase):
    """Verify services call the correct dispatch functions via on_commit."""

    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "1482767709279096893"
        self.event.auto_approve = True
        self.event.auto_confirm = True
        self.event.save()

    @patch("events.services.notify_signup_changed")
    def test_process_rsvp_dispatches_signup_changed(self, mock_notify):
        with self.captureOnCommitCallbacks(execute=True):
            process_rsvp(self.event, self.user)
        mock_notify.assert_called_once_with(self.event)

    @patch("events.services.notify_signup_changed")
    def test_approve_signup_dispatches_signup_changed(self, mock_notify):
        self.event.auto_approve = False
        self.event.save()
        with self.captureOnCommitCallbacks(execute=True):
            signup = process_rsvp(self.event, self.user)
        mock_notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            approve_signup(signup)
        mock_notify.assert_called_once()

    @patch("events.services.notify_signup_changed")
    def test_cancel_signup_dispatches_signup_changed(self, mock_notify):
        with self.captureOnCommitCallbacks(execute=True):
            signup = process_rsvp(self.event, self.user)
        mock_notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            cancel_signup(signup)
        mock_notify.assert_called_once()

    @patch("events.services.notify_signup_changed")
    def test_confirm_signup_dispatches_signup_changed(self, mock_notify):
        self.event.auto_approve = True
        self.event.auto_confirm = False
        self.event.roll_call_enabled = True
        self.event.require_mmr_verified = False
        self.event.require_steam_id = False
        self.event.require_profile_complete = False
        self.event.save()
        with self.captureOnCommitCallbacks(execute=True):
            signup = process_rsvp(self.event, self.user)
        mock_notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            confirm_signup(signup)
        mock_notify.assert_called_once()
