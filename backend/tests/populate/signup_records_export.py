"""Populate and reset only the sign-up records export browser scope."""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from events.constants import ActorRole, EventState, SignupMeans
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import cancel_event, process_rsvp, teardown_event
from org.models import Organization, OrgSettings
from tests.data.models import TestUser
from tests.data.signup_records_export import (
    EXPORT_EVENT_DAYS_AGO,
    EXPORT_EVENT_NAMES,
    SIGNUP_RECORDS_EXPORT_ORG,
    SIGNUP_RECORDS_EXPORT_USERS,
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


def _deleted_event_id(org_id: int) -> int | None:
    live = Event.objects.nocache().filter(organization_id=org_id).values("pk")
    return (
        SignupLedgerEntry.objects.filter(
            organization_id=org_id,
            event_snapshot__name=EXPORT_EVENT_NAMES["deleted"],
        )
        .exclude(event_id__in=live)
        .values_list("event_id", flat=True)
        .first()
    )


def _create_event(
    org: Organization, admin: CustomUser, name: str, days_ago: int
) -> Event:
    scheduled_at = timezone.now() - timedelta(days=days_ago)
    return Event.objects.create(
        organization=org,
        name=name,
        scheduled_at=scheduled_at,
        ends_at=scheduled_at + timedelta(hours=3),
        state=EventState.SIGNUPS_OPEN,
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


@transaction.atomic
def populate_signup_records_export_data(force: bool = False) -> None:
    staff, admin, member, *signers = [
        _ensure_user(data) for data in SIGNUP_RECORDS_EXPORT_USERS
    ]
    org, _ = Organization.objects.update_or_create(
        pk=SIGNUP_RECORDS_EXPORT_ORG.pk,
        defaults={
            "name": SIGNUP_RECORDS_EXPORT_ORG.name,
            "description": SIGNUP_RECORDS_EXPORT_ORG.description,
            "timezone": SIGNUP_RECORDS_EXPORT_ORG.timezone,
            "owner": admin,
            "discord_server_id": None,
        },
    )
    org.admins.set([admin])
    org.staff.set([staff])
    invalidate_obj(org)
    for user in (staff, admin, member, *signers):
        ensure_org_user(user, org, mmr=3000)

    live_names = set(
        Event.objects.nocache().filter(organization=org).values_list("name", flat=True)
    )
    expected_live = {EXPORT_EVENT_NAMES["kept"], EXPORT_EVENT_NAMES["cancelled"]}
    if not force and live_names == expected_live and _deleted_event_id(org.pk):
        return

    SignupLedgerEntry.objects.filter(organization_id=org.pk).purge()
    Event.objects.nocache().filter(organization=org).delete()
    OrgSettings.objects.filter(organization=org).delete()

    events: dict[str, Event] = {}
    for scenario, name in EXPORT_EVENT_NAMES.items():
        event = _create_event(org, admin, name, EXPORT_EVENT_DAYS_AGO[scenario])
        for signer in signers:
            process_rsvp(
                event,
                signer,
                actor=SignupActor(
                    user=signer, role=ActorRole.MEMBER, means=SignupMeans.WEB
                ),
            )
        events[scenario] = event
    cancel_event(events["cancelled"], actor=admin)
    teardown_event(events["deleted"], actor=admin, confirm_signup_records=True)
    for model in (Event, EventSignup, OrgSettings):
        invalidate_model(model)


def signup_records_export_test_data() -> dict[str, Any]:
    populate_signup_records_export_data()
    org_id = SIGNUP_RECORDS_EXPORT_ORG.pk
    events = dict(
        Event.objects.nocache().filter(organization_id=org_id).values_list("name", "pk")
    )
    staff, admin, member = SIGNUP_RECORDS_EXPORT_USERS[:3]
    return {
        "org_pk": org_id,
        "staff_pk": staff.pk,
        "admin_pk": admin.pk,
        "member_pk": member.pk,
        "kept_event_pk": events[EXPORT_EVENT_NAMES["kept"]],
        "cancelled_event_pk": events[EXPORT_EVENT_NAMES["cancelled"]],
        "deleted_event_pk": _deleted_event_id(org_id),
        "deleted_event_name": EXPORT_EVENT_NAMES["deleted"],
    }
