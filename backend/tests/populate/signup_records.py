"""Populate and reset only the signup-record preservation browser scope."""

from datetime import time, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from events.constants import ActorRole, EventState, SignupMeans
from events.ledger import SignupActor
from events.models import Event, EventRepeater, EventSignup, SignupLedgerEntry
from events.services import process_rsvp
from org.models import Organization
from tests.data.models import TestUser
from tests.data.signup_records import (
    SCENARIO_NAMES,
    SERIES_NAME,
    SIGNUP_RECORDS_ORG,
    SIGNUP_RECORDS_USERS,
)
from tests.populate.utils import ensure_org_user
from user.models import PositionsModel


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.steamid = data.get_steam_id_64()
    user.is_staff = False
    user.is_superuser = False
    user.save()
    return user


@transaction.atomic
def populate_signup_records_data(force: bool = False) -> None:
    admin, staff, member = [_ensure_user(data) for data in SIGNUP_RECORDS_USERS]
    org, _ = Organization.objects.update_or_create(
        pk=SIGNUP_RECORDS_ORG.pk,
        defaults={
            "name": SIGNUP_RECORDS_ORG.name,
            "description": SIGNUP_RECORDS_ORG.description,
            "timezone": "UTC",
            "owner": admin,
            "discord_server_id": None,
        },
    )
    org.admins.set([admin])
    org.staff.set([staff])
    invalidate_obj(org)
    for user in (admin, staff, member):
        ensure_org_user(user, org, mmr=3000)
    existing = set(
        Event.objects.nocache().filter(organization=org).values_list("name", flat=True)
    )
    if not force and existing == set(SCENARIO_NAMES.values()):
        return

    # This test-only org owns its orphan history as well as its live scenarios.
    SignupLedgerEntry.objects.filter(organization_id=org.pk).purge()
    Event.objects.nocache().filter(organization=org).delete()
    EventRepeater.objects.nocache().filter(organization=org).delete()
    start = timezone.now() + timedelta(days=7)
    repeater = EventRepeater.objects.create(
        organization=org,
        name=SERIES_NAME,
        starts_at=start.date(),
        time_of_day=time(20, 0),
        day_of_week=1,
        timezone="UTC",
        created_by=admin,
    )
    for index, (scenario, name) in enumerate(SCENARIO_NAMES.items()):
        scheduled_at = start + timedelta(days=index)
        event = Event.objects.create(
            organization=org,
            name=name,
            scheduled_at=scheduled_at,
            ends_at=scheduled_at + timedelta(hours=3),
            state=EventState.SIGNUPS_OPEN,
            event_repeater=repeater if scenario in {"registered", "empty"} else None,
            created_by=admin,
            auto_approve=True,
            allow_user_signups=True,
            require_steam_id=False,
            require_mmr_verified=False,
            require_profile_complete=False,
            max_players=10,
            discord_announcement=False,
            discord_mark_interested=False,
        )
        if scenario != "empty":
            process_rsvp(
                event,
                member,
                actor=SignupActor(
                    user=member, role=ActorRole.MEMBER, means=SignupMeans.WEB
                ),
            )
    for model in (Event, EventRepeater, EventSignup):
        invalidate_model(model)


def signup_records_test_data() -> dict[str, Any]:
    populate_signup_records_data()
    org_id = SIGNUP_RECORDS_ORG.pk
    events = dict(
        Event.objects.nocache().filter(organization_id=org_id).values_list("name", "pk")
    )
    return {
        "org_pk": org_id,
        "admin_pk": SIGNUP_RECORDS_USERS[0].pk,
        "staff_pk": SIGNUP_RECORDS_USERS[1].pk,
        "member_pk": SIGNUP_RECORDS_USERS[2].pk,
        **{
            f"{scenario}_event_pk": events[name]
            for scenario, name in SCENARIO_NAMES.items()
        },
        "repeater_pk": EventRepeater.objects.nocache()
        .get(organization_id=org_id, name=SERIES_NAME)
        .pk,
    }
