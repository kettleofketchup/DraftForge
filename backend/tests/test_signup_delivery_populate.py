from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import (
    DiscordEventLog,
    DiscordMessageLog,
    SignupPostDeliveryState,
)
from events.models import Event
from tests.populate.signup_delivery import populate_signup_delivery


class SignupDeliveryPopulateTest(TestCase):
    @patch("requests.request")
    def test_repeat_population_preserves_uncertain_first_delivery(
        self, request: Mock
    ) -> None:
        populate_signup_delivery()
        event = Event.objects.nocache().get(name="Signup Delivery Uncertain Event")
        populate_signup_delivery()
        self.assertEqual(
            list(
                Event.objects.nocache()
                .filter(name=event.name)
                .values_list("pk", flat=True)
            ),
            [event.pk],
        )
        state = SignupPostDeliveryState.objects.get(event=event)
        self.assertEqual(state.state, "uncertain")
        self.assertEqual(state.attempts, 1)
        self.assertIsNone(state.receipt)
        self.assertFalse(
            DiscordMessageLog.objects.filter(source_id=event.pk, success=True).exists()
        )
        self.assertFalse(
            DiscordEventLog.objects.filter(
                discord_event__event=event, success=True
            ).exists()
        )
        client = APIClient()
        staff = CustomUser.objects.get(username="signup_delivery_staff")
        member = CustomUser.objects.get(username="signup_delivery_member")
        self.assertTrue(event.organization.staff.filter(pk=staff.pk).exists())
        self.assertFalse(member.is_staff)
        self.assertFalse(member.is_superuser)
        self.assertFalse(event.organization.staff.filter(pk=member.pk).exists())
        client.force_authenticate(staff)
        response = client.get(f"/api/events/{event.pk}/task-schedule/")
        self.assertEqual(response.status_code, 200)
        signup = next(
            entry for entry in response.data if entry["task"] == "signup_post"
        )
        self.assertIn(signup["status"], ("ready", "pending"))
        self.assertTrue(signup["can_fire"])
        discord_response = client.get(f"/api/events/{event.pk}/discord/")
        self.assertEqual(discord_response.status_code, 200)
        self.assertEqual(discord_response.data["logs"], [])
        self.assertIsNone(discord_response.data["signup_message"])
        request.assert_not_called()
