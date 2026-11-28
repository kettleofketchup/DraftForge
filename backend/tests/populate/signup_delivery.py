"""Synthetic, send-free data for signup delivery confirmation tests."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_obj
from app.models import CustomUser
from discordbot.models import (
    DiscordEvent,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)
from events.constants import EventState
from events.models import Event
from org.models import Organization
from tests.populate.utils import ensure_org_user
from user.models import PositionsModel

STAFF_PK = 9400
MEMBER_PK = 9401
EVENT_NAME = "Signup Delivery Uncertain Event"


@transaction.atomic
def populate_signup_delivery(force: bool = False) -> None:
    users: list[CustomUser] = []
    for pk, username in (
        (STAFF_PK, "signup_delivery_staff"),
        (MEMBER_PK, "signup_delivery_member"),
    ):
        user, created = CustomUser.objects.get_or_create(
            pk=pk, defaults={"username": username}
        )
        if created:
            user.positions = PositionsModel.objects.create()
            user.set_unusable_password()
            user.save()
        users.append(user)
    staff = users[0]
    org, _ = Organization.objects.get_or_create(name="Signup Delivery Test Org")
    org.staff.add(staff)
    invalidate_obj(org)
    for user in users:
        ensure_org_user(user, org)
    start = timezone.now() + timedelta(days=7)
    event, _ = Event.objects.get_or_create(
        organization=org,
        name=EVENT_NAME,
        defaults={
            "scheduled_at": start,
            "ends_at": start + timedelta(hours=2),
            "state": EventState.SIGNUPS_OPEN,
            "created_by": staff,
            "discord_announcement": False,
            "discord_post_signups": True,
            "discord_post_signups_channel_id": "900000000000000001",
        },
    )
    DiscordEvent.objects.get_or_create(
        event=event, defaults={"guild_id": "900000000000000002"}
    )
    SignupPostDeliveryState.objects.get_or_create(
        event=event,
        defaults={"state": SignupDeliveryStatus.UNCERTAIN, "attempts": 1},
    )
