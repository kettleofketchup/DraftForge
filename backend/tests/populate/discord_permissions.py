"""Populate the Discord permission badge E2E data (tests.data.discord_permissions).

populate_discord_permissions_data creates org/league 70, users 9100-9102 and
a fresh and a posted event. It writes rows only: the org's Discord server id
is set with a queryset update so no signal enqueues work, and no Discord task
is dispatched. discord_permissions_test_data is the lookup the spec reads.
"""

from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from discordbot.models import DiscordEvent, DiscordEventMsgSignup, DiscordMessageLog
from discordbot.permissions.reader import FIXTURE_TOKEN_FP
from events.constants import EventState
from events.models import Event
from league.models import League
from org.models import Organization
from tests.data.discord_permissions import (
    PERMISSION_ANNOUNCEMENT_CHANNEL_ID,
    PERMISSION_ATTENDANCE_CHANNEL_ID,
    PERMISSION_DEFAULT_SCENARIO,
    PERMISSION_EVENT_NAMES,
    PERMISSION_FRESH_EVENT_NAME,
    PERMISSION_GUILD_ID,
    PERMISSION_HISTORY_CHANNEL_ID,
    PERMISSION_HISTORY_THREAD_ID,
    PERMISSION_LEAGUE,
    PERMISSION_LEAGUE_STAFF,
    PERMISSION_ORG,
    PERMISSION_OUTSIDER,
    PERMISSION_POSTED_EVENT_NAME,
    PERMISSION_SCHEDULED_EVENT_ID,
    PERMISSION_SIGNUP_MESSAGE_ID,
    PERMISSION_STAFF,
    PERMISSION_USERS,
    permission_scenario,
)
from tests.data.models import TestUser
from tests.populate.utils import delete_events
from user.models import PositionsModel

FIXTURE_KEY: str = f"discord_perm_fixture:{PERMISSION_GUILD_ID}"


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.save()
    return user


def _ensure_org_and_league(
    staff: CustomUser, league_staff: CustomUser
) -> tuple[Organization, League]:
    org, _ = Organization.objects.update_or_create(
        pk=PERMISSION_ORG.pk,
        defaults={
            "name": PERMISSION_ORG.name,
            "description": PERMISSION_ORG.description,
            "logo": "",
            "timezone": PERMISSION_ORG.timezone,
        },
    )
    Organization.objects.filter(pk=org.pk).update(
        discord_server_id=PERMISSION_ORG.discord_server_id
    )
    league, _ = League.objects.update_or_create(
        pk=PERMISSION_LEAGUE.pk,
        defaults={
            "steam_league_id": PERMISSION_LEAGUE.steam_league_id,
            "name": PERMISSION_LEAGUE.name,
            "organization": org,
            "timezone": PERMISSION_LEAGUE.timezone,
        },
    )
    org.staff.set([staff])
    org.admins.clear()
    league.staff.set([league_staff])
    league.admins.clear()
    invalidate_obj(org)
    invalidate_obj(league)
    return org, league


def _create_event(
    org: Organization, league: League, staff: CustomUser, name: str
) -> Event:
    start = (timezone.now() + timedelta(days=14)).replace(
        minute=0, second=0, microsecond=0
    )
    return Event.objects.create(
        organization=org,
        tournament_league=league,
        name=name,
        tournament_name=f"{name} Tournament",
        description="Event whose Discord permission badges the E2E tests read.",
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=EventState.SIGNUPS_OPEN,
        allow_user_signups=True,
        discord_announcement=True,
        discord_announcement_channel_id=PERMISSION_ANNOUNCEMENT_CHANNEL_ID,
        discord_confirm_attendance=True,
        discord_confirm_attendance_channel_id=PERMISSION_ATTENDANCE_CHANNEL_ID,
        discord_create_event=True,
        discord_mark_interested=True,
        discord_signup_reminder=True,
        discord_post_signups=False,
        discord_start_mention=False,
        created_by=staff,
    )


def _mark_posted(event: Event) -> None:
    signup = DiscordEventMsgSignup.objects.create(
        event=event,
        channel_id=PERMISSION_HISTORY_CHANNEL_ID,
        thread_id=PERMISSION_HISTORY_THREAD_ID,
        message_id=PERMISSION_SIGNUP_MESSAGE_ID,
        has_posted=True,
        message_last_updated=timezone.now(),
    )
    DiscordEvent.objects.create(
        event=event,
        guild_id=PERMISSION_GUILD_ID,
        scheduled_event_id=PERMISSION_SCHEDULED_EVENT_ID,
        signup_message=signup,
    )


def _events(org_pk: int) -> Any:
    return Event.objects.nocache().filter(
        organization_id=org_pk, name__in=PERMISSION_EVENT_NAMES
    )


def permission_snapshot_keys() -> list[str]:
    """Every reader cache key the fixture guild's scenarios can write."""
    scope = f"{FIXTURE_TOKEN_FP}:{PERMISSION_GUILD_ID}"
    channels = (
        PERMISSION_ANNOUNCEMENT_CHANNEL_ID,
        PERMISSION_ATTENDANCE_CHANNEL_ID,
        PERMISSION_HISTORY_CHANNEL_ID,
        PERMISSION_HISTORY_THREAD_ID,
    )
    kinds = ["bot", "guild", "member", "channels"]
    kinds.append(f"event:{PERMISSION_SCHEDULED_EVENT_ID}")
    for channel in channels:
        kinds += [
            f"channel:{channel}",
            f"thread-member:{channel}",
            f"message:{channel}:{PERMISSION_SIGNUP_MESSAGE_ID}",
        ]
    return [
        f"discord_perm_refresh:{scope}",
        f"discord_perm_generation:{scope}",
        *(f"discord_perm:v1:{scope}:{kind}" for kind in kinds),
        *(f"discord_perm_channel_fence:{scope}:{channel}" for channel in channels),
    ]


def clear_permission_snapshots() -> None:
    cache.delete_many(permission_snapshot_keys())


def set_permission_scenario(name: str) -> None:
    """Serve the named canned scenario for the org's guild; KeyError if unknown."""
    cache.set(FIXTURE_KEY, permission_scenario(name), timeout=None)
    clear_permission_snapshots()


@transaction.atomic
def populate_discord_permissions_data(force: bool = False) -> None:
    """Create the permission badge org, league, users and two events.

    Users, org and league are updated in place. `force` rebuilds the events.
    """
    print("  Populating Discord permission badge E2E data...")
    users = {data.pk: _ensure_user(data) for data in PERMISSION_USERS}
    staff = users[PERMISSION_STAFF.pk]
    org, league = _ensure_org_and_league(staff, users[PERMISSION_LEAGUE_STAFF.pk])
    if force:
        delete_events(_events(org.pk))
    existing = set(_events(org.pk).values_list("name", flat=True))
    if PERMISSION_FRESH_EVENT_NAME not in existing:
        _create_event(org, league, staff, PERMISSION_FRESH_EVENT_NAME)
    if PERMISSION_POSTED_EVENT_NAME not in existing:
        _mark_posted(_create_event(org, league, staff, PERMISSION_POSTED_EVENT_NAME))
    for model in (Event, DiscordEvent, DiscordEventMsgSignup):
        invalidate_model(model)
    print(
        f"    Created {PERMISSION_ORG.name} with {len(PERMISSION_EVENT_NAMES)} events"
    )


def reset_discord_permissions_data() -> None:
    populate_discord_permissions_data(force=True)
    set_permission_scenario(PERMISSION_DEFAULT_SCENARIO)


def discord_permissions_test_data() -> dict[str, Any]:
    """PKs and channel ids the spec looks up (never hardcoded there)."""
    events = dict(_events(PERMISSION_ORG.pk).values_list("name", "pk"))
    return {
        "org_pk": PERMISSION_ORG.pk,
        "league_pk": PERMISSION_LEAGUE.pk,
        "fresh_event_pk": events[PERMISSION_FRESH_EVENT_NAME],
        "posted_event_pk": events[PERMISSION_POSTED_EVENT_NAME],
        "staff_pk": PERMISSION_STAFF.pk,
        "league_staff_pk": PERMISSION_LEAGUE_STAFF.pk,
        "outsider_pk": PERMISSION_OUTSIDER.pk,
        "channel_ids": {
            "announcement": PERMISSION_ANNOUNCEMENT_CHANNEL_ID,
            "attendance": PERMISSION_ATTENDANCE_CHANNEL_ID,
            "historical_thread": PERMISSION_HISTORY_THREAD_ID,
        },
        "message_log_count": DiscordMessageLog.objects.filter(
            source_id__in=list(events.values())
        ).count(),
    }
