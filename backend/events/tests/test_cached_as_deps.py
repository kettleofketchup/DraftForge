from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DMType,
)
from events import views
from events.models import Event, EventRepeater, EventSignup
from org.models import Organization, OrgUser
from tests.cached_as_reads import record_cached_as


class EventsCachedAsDepsTest(TestCase):
    """Every model an events @cached_as body reads is one of its deps."""

    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="ecad_owner")
        org = Organization.objects.create(name="ECAD Org", owner=self.owner)
        host = CustomUser.objects.create_user(username="ecad_host", discordId="555")
        helper = CustomUser.objects.create_user(username="ecad_helper")
        org_user = OrgUser.objects.create(
            user=host, organization=org, guild_nickname="Claw"
        )
        self.repeater = EventRepeater.objects.create(
            organization=org,
            name="ECAD Series",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        self.event = Event.objects.create(
            organization=org,
            name="ECAD Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            host=host,
            event_repeater=self.repeater,
        )
        self.event.helpers.add(helper)
        EventSignup.objects.create(event=self.event, user=helper)
        discord_event = DiscordEvent.objects.create(
            event=self.event,
            guild_id="g1",
            signup_message=DiscordEventMsgSignup.objects.create(
                event=self.event, channel_id="1"
            ),
            announcement=DiscordEventMsgAnnouncement.objects.create(
                event=self.event, channel_id="1"
            ),
        )
        message_log = DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={},
            success=True,
            source="event_announcement",
            source_id=self.event.pk,
            fired_by=host,
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="rsvp",
            discord_user_id=host.discordId,
            message_log=message_log,
        )
        DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_cached_bodies_declare_every_model_they_read(self) -> None:
        # select_related joins whose rows only contribute a pk to the payload.
        join_only = {
            "/api/events/": {"CustomUser", "League", "Tournament"},
            f"/api/events/{self.event.pk}/": {"League", "Tournament"},
            f"/api/events/{self.event.pk}/discord/": set(),
            # is_subscribed is per user and merged after the cache lookup.
            "/api/events/repeaters/": {"CustomUser", "League"},
            f"/api/events/repeaters/{self.repeater.pk}/": {"CustomUser", "League"},
        }
        for path, ignored in join_only.items():
            with self.subTest(path=path), record_cached_as(views) as calls:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(len(calls), 1)
                missing = sorted(
                    m.__name__
                    for m in calls[0].uncovered_reads()
                    if m.__name__ not in ignored
                )
                self.assertEqual(missing, [], f"{path} reads undeclared models")
