from django.test import TestCase
from django.urls import resolve, Resolver404


class SignupUrlConfTest(TestCase):
    """Pin that /signup/ resolves and the deleted /rsvp/ /tentative/ do not."""

    def test_signup_endpoint_resolves_to_signup_action(self):
        match = resolve("/api/events/1/signup/")
        # DRF action URLs resolve to ViewSet.as_view({...method: action_name}).
        self.assertEqual(match.func.actions["post"], "signup")

    def test_old_rsvp_endpoint_does_not_resolve(self):
        with self.assertRaises(Resolver404):
            resolve("/api/events/1/rsvp/")

    def test_old_tentative_endpoint_does_not_resolve(self):
        with self.assertRaises(Resolver404):
            resolve("/api/events/1/tentative/")
