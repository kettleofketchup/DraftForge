"""Regression test — EventViewSet.perform_update invalidates the event's cache.

Existing implementation already calls invalidate_after_commit(event); this
test locks that in so a future refactor doesn't silently remove it. The
fire path's next 30s poll relies on cacheops being current so edits to
reminder timing fields take effect promptly.
"""

from unittest.mock import patch

from rest_framework.test import APIClient

from events.tests.test_discord_tasks import _DiscordTaskTestCase


class EventEditInvalidatesCacheTest(_DiscordTaskTestCase):
    @patch("app.cache_utils.invalidate_after_commit")
    def test_perform_update_invalidates_event(self, mock_invalidate):
        client = APIClient()
        client.force_authenticate(user=self.admin)  # admin has org-staff access
        response = client.patch(
            f"/api/events/{self.event.pk}/",
            {"name": "Edited"},
            format="json",
        )
        self.assertIn(response.status_code, (200, 202))

        # invalidate_after_commit was called with self.event (or a refreshed
        # instance) — at minimum, somewhere in the call list, the event PK
        # appears among the args.
        called_with_event = any(
            getattr(arg, "pk", None) == self.event.pk
            for call in mock_invalidate.call_args_list
            for arg in call.args
        )
        self.assertTrue(
            called_with_event,
            f"invalidate_after_commit not called with event pk {self.event.pk}; "
            f"call args were: {mock_invalidate.call_args_list}",
        )
