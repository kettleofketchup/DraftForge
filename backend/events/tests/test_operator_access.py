from django.contrib.auth.models import AnonymousUser

from events.permissions import has_event_operator_access, has_event_staff_access
from events.tests.base import EventTestCase


class EventOperatorAccessTests(EventTestCase):
    def test_org_staff_allowed(self) -> None:
        self.assertTrue(has_event_operator_access(self.admin, self.event))

    def test_league_staff_allowed_on_league_event(self) -> None:
        self.assertTrue(has_event_operator_access(self.league_staff, self.event))

    def test_host_allowed(self) -> None:
        host = self.make_user()
        event = self.make_event(host=host)
        self.assertTrue(has_event_operator_access(host, event))

    def test_helper_allowed(self) -> None:
        helper = self.make_user()
        self.event.helpers.add(helper)
        self.assertTrue(has_event_operator_access(helper, self.event))

    def test_anonymous_and_none_denied(self) -> None:
        self.assertFalse(has_event_operator_access(AnonymousUser(), self.event))
        self.assertFalse(has_event_operator_access(None, self.event))

    def test_unrelated_user_denied(self) -> None:
        self.assertFalse(has_event_operator_access(self.unrelated_user, self.event))

    def test_promoter_denied(self) -> None:
        promoter = self.make_user()
        self.org.promoters.add(promoter)
        self.assertFalse(has_event_operator_access(promoter, self.event))

    def test_host_of_other_event_denied(self) -> None:
        host = self.make_user()
        self.make_event(host=host)
        self.assertFalse(has_event_operator_access(host, self.event))

    def test_helper_of_other_event_denied(self) -> None:
        helper = self.make_user()
        other = self.make_event()
        other.helpers.add(helper)
        self.assertFalse(has_event_operator_access(helper, self.event))

    def test_removed_helper_loses_access(self) -> None:
        helper = self.make_user()
        self.event.helpers.add(helper)
        self.assertTrue(has_event_operator_access(helper, self.event))
        self.event.helpers.remove(helper)
        self.assertFalse(has_event_operator_access(helper, self.event))

    def test_staff_helper_untouched(self) -> None:
        helper = self.make_user()
        self.event.helpers.add(helper)
        self.assertFalse(has_event_staff_access(helper, self.event))
