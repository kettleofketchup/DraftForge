from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from app.models import CustomUser
from events.constants import SignupStatus
from events.models import EventSignup, SignupLedgerEntry
from events.tests.base import EventTestCase

LOCKED_FIELDS: tuple[str, ...] = (
    "status",
    "user",
    "event",
    "event_team",
    "signup_type",
    "waitlist_position",
)


class EventSignupAdminLockTests(EventTestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="signup_admin_lock_su", password="pw", email="lock@example.com"
        )
        self.signup = EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.APPROVED
        )
        self.model_admin = admin.site._registry[EventSignup]
        self.request = RequestFactory().get("/")
        self.request.user = self.superuser

    def test_state_fields_are_readonly(self) -> None:
        readonly = self.model_admin.get_readonly_fields(self.request, self.signup)
        for name in LOCKED_FIELDS:
            with self.subTest(field=name):
                self.assertIn(name, readonly)
        form_class = self.model_admin.get_form(self.request, self.signup)
        for name in LOCKED_FIELDS:
            with self.subTest(form_field=name):
                self.assertNotIn(name, form_class.base_fields)

    def test_add_is_disabled(self) -> None:
        self.assertFalse(self.model_admin.has_add_permission(self.request))
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:events_eventsignup_add"))
        self.assertEqual(response.status_code, 403)

    def test_delete_stays_allowed(self) -> None:
        self.assertTrue(
            self.model_admin.has_delete_permission(self.request, self.signup)
        )

    def test_change_view_renders(self) -> None:
        self.client.force_login(self.superuser)
        url = reverse("admin:events_eventsignup_change", args=[self.signup.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_post_cannot_change_status(self) -> None:
        self.client.force_login(self.superuser)
        url = reverse("admin:events_eventsignup_change", args=[self.signup.pk])
        entries_before = SignupLedgerEntry.objects.count()
        response = self.client.post(
            url,
            {
                "status": SignupStatus.CANCELLED,
                "user": self.admin.pk,
                "event": self.event.pk,
                "signup_type": "team",
                "waitlist_position": "7",
                "unmet_requirements": "[]",
                "eligibility_reasons": "[]",
                "eligibility_checked_at_0": "",
                "eligibility_checked_at_1": "",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, SignupStatus.APPROVED)
        self.assertEqual(self.signup.user_id, self.user.pk)
        self.assertEqual(self.signup.event_id, self.event.pk)
        self.assertEqual(self.signup.signup_type, "user")
        self.assertIsNone(self.signup.waitlist_position)
        self.assertEqual(SignupLedgerEntry.objects.count(), entries_before)
