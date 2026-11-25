"""Populate the signup history E2E data (tests.data.signup_history).

populate_signup_history_data creates org 60, users 9000-9006 and an event
whose signup changes all go through the events services, so the ledger holds
real entries. signup_history_test_data is the lookup the specs read.
"""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from events.constants import ActorRole, EventState, SignupMeans
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import cancel_signup, process_rsvp, staff_add_signup
from org.models import Organization
from tests.data.models import TestUser
from tests.data.signup_history import (
    SIGNUP_HISTORY_BUTTON,
    SIGNUP_HISTORY_EVENT_NAME,
    SIGNUP_HISTORY_LONG_NICK,
    SIGNUP_HISTORY_MEMBERS,
    SIGNUP_HISTORY_ORG,
    SIGNUP_HISTORY_OUTSIDER,
    SIGNUP_HISTORY_REACTION,
    SIGNUP_HISTORY_REASON,
    SIGNUP_HISTORY_STAFF,
    SIGNUP_HISTORY_STAFF_ADDED,
    SIGNUP_HISTORY_USERS,
    SIGNUP_HISTORY_WITHDRAWER,
)
from tests.populate.utils import ensure_org_user
from user.models import PositionsModel

_MEMBER_MMR = 3000


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.steamid = data.get_steam_id_64()
    user.save()
    return user


def _ensure_org(staff: CustomUser) -> Organization:
    org, _ = Organization.objects.update_or_create(
        pk=SIGNUP_HISTORY_ORG.pk,
        defaults={
            "name": SIGNUP_HISTORY_ORG.name,
            "description": SIGNUP_HISTORY_ORG.description,
            "logo": "",
            "timezone": SIGNUP_HISTORY_ORG.timezone,
        },
    )
    org.admins.add(staff)
    invalidate_obj(org)
    return org


def _delete_event(org: Organization) -> None:
    event_ids = list(
        Event.objects.nocache()
        .filter(organization=org, name=SIGNUP_HISTORY_EVENT_NAME)
        .values_list("pk", flat=True)
    )
    if not event_ids:
        return
    SignupLedgerEntry.objects.filter(event_id__in=event_ids).purge()
    Event.objects.nocache().filter(pk__in=event_ids).delete()


def _signup(event: Event, user: CustomUser) -> EventSignup:
    return EventSignup.objects.nocache().get(event=event, user=user)


def _run_history(event: Event, users: dict[int, CustomUser]) -> None:
    staff = users[SIGNUP_HISTORY_STAFF.pk]
    withdrawer = users[SIGNUP_HISTORY_WITHDRAWER.pk]
    button = users[SIGNUP_HISTORY_BUTTON.pk]
    reaction = users[SIGNUP_HISTORY_REACTION.pk]
    long_nick = users[SIGNUP_HISTORY_LONG_NICK.pk]
    staff_added = users[SIGNUP_HISTORY_STAFF_ADDED.pk]

    def web(user: CustomUser) -> SignupActor:
        return SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)

    process_rsvp(event, withdrawer, actor=web(withdrawer))
    process_rsvp(
        event,
        button,
        actor=SignupActor.discord(button, correlation_id="populate-history-1"),
    )
    process_rsvp(
        event,
        reaction,
        actor=SignupActor.discord(
            reaction,
            means=SignupMeans.DISCORD_REACTION,
            correlation_id=f"reaction:populate:{reaction.pk}",
        ),
    )
    cancel_signup(_signup(event, withdrawer), actor=web(withdrawer))
    process_rsvp(event, withdrawer, actor=web(withdrawer))
    process_rsvp(event, long_nick, actor=web(long_nick))
    staff_add_signup(
        event,
        staff_added,
        actor=SignupActor(user=staff, role=ActorRole.STAFF, means=SignupMeans.WEB),
        reason=SIGNUP_HISTORY_REASON,
    )


@transaction.atomic
def populate_signup_history_data(force: bool = False) -> None:
    """Create the signup history org, users and event with ledger entries.

    Users are updated in place. `force` rebuilds the event and its ledger.
    """
    print("  Populating signup history E2E data...")
    users = {data.pk: _ensure_user(data) for data in SIGNUP_HISTORY_USERS}
    org = _ensure_org(users[SIGNUP_HISTORY_STAFF.pk])
    ensure_org_user(users[SIGNUP_HISTORY_STAFF.pk], org)
    for data in SIGNUP_HISTORY_MEMBERS:
        ensure_org_user(users[data.pk], org, mmr=_MEMBER_MMR)

    if force:
        _delete_event(org)
    if (
        Event.objects.nocache()
        .filter(organization=org, name=SIGNUP_HISTORY_EVENT_NAME)
        .exists()
    ):
        return

    start = timezone.now() + timedelta(days=7)
    event = Event.objects.create(
        organization=org,
        name=SIGNUP_HISTORY_EVENT_NAME,
        description="Event whose signup ledger the signup history E2E tests read.",
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=EventState.SIGNUPS_OPEN,
        allow_user_signups=True,
        max_players=2,
        discord_announcement=False,
        discord_mark_interested=False,
        created_by=users[SIGNUP_HISTORY_STAFF.pk],
    )
    _run_history(event, users)
    for model in (Event, EventSignup):
        invalidate_model(model)
    print(f"    Created {SIGNUP_HISTORY_EVENT_NAME} with ledger entries")


def signup_history_test_data() -> dict[str, Any]:
    """PKs the specs look up by role (never hardcoded there)."""
    event = Event.objects.nocache().get(
        organization_id=SIGNUP_HISTORY_ORG.pk, name=SIGNUP_HISTORY_EVENT_NAME
    )
    return {
        "org_pk": SIGNUP_HISTORY_ORG.pk,
        "event_pk": event.pk,
        "staff_pk": SIGNUP_HISTORY_STAFF.pk,
        "outsider_pk": SIGNUP_HISTORY_OUTSIDER.pk,
        "member_pks": [data.pk for data in SIGNUP_HISTORY_MEMBERS],
        "withdrawer_pk": SIGNUP_HISTORY_WITHDRAWER.pk,
        "promoted_pk": SIGNUP_HISTORY_REACTION.pk,
        "staff_added_pk": SIGNUP_HISTORY_STAFF_ADDED.pk,
        "long_nick_pk": SIGNUP_HISTORY_LONG_NICK.pk,
        "discord_button_pk": SIGNUP_HISTORY_BUTTON.pk,
        "reaction_pk": SIGNUP_HISTORY_REACTION.pk,
    }
