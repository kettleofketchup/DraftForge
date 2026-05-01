import calendar
import datetime
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from cacheops import invalidate_obj
from django.db import models, transaction

from app.cache_utils import invalidate_after_commit
from app.models import Tournament
from events.constants import EventState, RepeatFrequency, SignupStatus, SignupType
from events.discord import (
    notify_mark_interested,
    notify_new_event,
    notify_signup_changed,
)
from events.models import (
    DiscordEventConfigMixin,
    Event,
    EventConfigMixin,
    EventSignup,
    TournamentTemplateMixin,
)

logger = logging.getLogger(__name__)


def check_requirements(event, user):
    """Check if user meets event confirmation requirements."""
    from org.models import OrgUser
    from org.models_profiles import PlayerDotaProfile

    if event.require_steam_id and not user.steamid:
        return False
    if event.require_mmr_verified:
        try:
            org_user = OrgUser.objects.get(user=user, organization=event.organization)
            if not org_user.has_active_dota_mmr:
                return False
        except OrgUser.DoesNotExist:
            return False

    # Check rank type restrictions and screenshot requirements (Dota 2 only)
    try:
        org_user = OrgUser.objects.get(user=user, organization=event.organization)
        profile = PlayerDotaProfile.objects.get(org_user=org_user)

        # Rank type allowed?
        if profile.rank_status == "active" and not event.allow_active_mmr:
            return False
        if profile.rank_status == "previous" and not event.allow_previous_rank:
            return False
        if profile.rank_status == "never" and not event.allow_battlecup_rating:
            return False

        # Screenshot required but missing?
        if event.discord_require_rank_screenshot and profile.rank_status in (
            "active",
            "previous",
        ):
            if not profile.rank_screenshot:
                return False
        if (
            event.discord_require_battlecup_screenshot
            and profile.rank_status == "never"
        ):
            if not profile.battlecup_screenshot:
                return False

        # Min MMR check
        if event.min_mmr and profile.rank_status == "active":
            if not profile.mmr or profile.mmr < event.min_mmr:
                return False
    except (OrgUser.DoesNotExist, PlayerDotaProfile.DoesNotExist):
        pass  # No profile = skip Dota-specific checks

    if event.require_profile_complete:
        if not (user.nickname and user.steamid and user.discordId):
            return False
    return True


def _get_active_signup_count(event):
    """Count non-cancelled, non-rejected, non-waitlisted signups."""
    return (
        EventSignup.objects.filter(event=event)
        .exclude(
            status__in=[
                SignupStatus.CANCELLED,
                SignupStatus.REJECTED,
                SignupStatus.WAITLISTED,
            ],
        )
        .count()
    )


@transaction.atomic
def _create_signup(event, user, event_team=None):
    """Internal: create a signup with no state check.

    Handles existing-signup detection, waitlist placement, auto-approve / auto-confirm,
    tournament addition, and notify hooks. State authorization is the caller's job.

    INVARIANT: invalidate_after_commit MUST be registered before any transaction.on_commit
    notify hook. Notify handlers may re-query, and reading through a stale cache would
    re-warm it with stale data.
    """
    existing = EventSignup.objects.filter(event=event, user=user).first()
    if existing:
        logger.info(
            "Existing signup found: user=%s, event=%s, status=%s, id=%s",
            user.pk,
            event.pk,
            existing.status,
            existing.id,
        )
        if existing.status in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            existing.delete()
            logger.info("Deleted cancelled/rejected signup, allowing re-RSVP")
        elif existing.status == SignupStatus.TENTATIVE:
            existing.delete()
            logger.info("Upgrading tentative signup to full RSVP")
        else:
            raise ValueError("User has already signed up for this event.")

    signup_type = SignupType.TEAM if event_team else SignupType.USER

    if event.max_players and _get_active_signup_count(event) >= event.max_players:
        max_pos = (
            EventSignup.objects.filter(event=event, status=SignupStatus.WAITLISTED)
            .order_by("-waitlist_position")
            .values_list("waitlist_position", flat=True)
            .first()
        ) or 0
        signup = EventSignup.objects.create(
            event=event,
            user=user,
            event_team=event_team,
            signup_type=signup_type,
            status=SignupStatus.WAITLISTED,
            waitlist_position=max_pos + 1,
        )
        invalidate_after_commit(event)
        transaction.on_commit(lambda: notify_signup_changed(event))
        return signup

    status = SignupStatus.RSVP
    if event.auto_approve:
        if check_requirements(event, user):
            status = SignupStatus.APPROVED
            if event.auto_confirm:
                status = SignupStatus.CONFIRMED
        else:
            status = SignupStatus.PENDING_APPROVAL

    signup = EventSignup.objects.create(
        event=event,
        user=user,
        event_team=event_team,
        signup_type=signup_type,
        status=status,
    )
    if status == SignupStatus.CONFIRMED:
        add_user_to_tournament(event, user)
    elif status == SignupStatus.APPROVED and not event.roll_call_enabled:
        add_user_to_tournament(event, user)
    invalidate_after_commit(event)
    transaction.on_commit(lambda: notify_signup_changed(event))
    if status in (SignupStatus.CONFIRMED, SignupStatus.APPROVED):
        transaction.on_commit(lambda: notify_mark_interested(event, user.pk))
    return signup


def process_rsvp(event, user, event_team=None):
    """Public-path signup. Locked to SIGNUPS_OPEN."""
    if event.state != EventState.SIGNUPS_OPEN:
        raise ValueError("Event is not accepting signups.")
    return _create_signup(event, user, event_team=event_team)


def staff_add_signup(event, user, event_team=None):
    """Staff-path signup. Allowed during SIGNUPS_OPEN or ROLL_CALL."""
    if event.state not in (EventState.SIGNUPS_OPEN, EventState.ROLL_CALL):
        raise ValueError("Event is not accepting signups.")
    return _create_signup(event, user, event_team=event_team)


APPROVABLE_STATUSES = [
    SignupStatus.RSVP,
    SignupStatus.PENDING_APPROVAL,
    SignupStatus.WAITLISTED,
]


@transaction.atomic
def approve_signup(signup, mmr_override=None):
    """Approve a signup, optionally setting the user's MMR."""
    from django.utils import timezone as tz

    from org.models import OrgUser

    if signup.status not in APPROVABLE_STATUSES:
        raise ValueError(f"Cannot approve signup in '{signup.status}' status.")

    # Apply MMR override when provided by an admin
    if mmr_override is not None:
        try:
            org_user = OrgUser.objects.get(
                user=signup.user, organization=signup.event.organization
            )
        except OrgUser.DoesNotExist:
            raise ValueError("User is not a member of this organization.")
        org_user.mmr = mmr_override
        org_user.has_active_dota_mmr = True
        org_user.dota_mmr_last_verified = tz.now()
        org_user.save(
            update_fields=["mmr", "has_active_dota_mmr", "dota_mmr_last_verified"]
        )
        invalidate_after_commit(org_user)

    signup.status = SignupStatus.APPROVED
    signup.waitlist_position = None
    signup.save(update_fields=["status", "waitlist_position", "updated_at"])
    # If no roll call, approved means ready for tournament
    if not signup.event.roll_call_enabled:
        add_user_to_tournament(signup.event, signup.user)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def reject_signup(signup):
    """Reject a signup."""
    if signup.status in [SignupStatus.REJECTED, SignupStatus.CANCELLED]:
        raise ValueError(f"Cannot reject signup in '{signup.status}' status.")
    signup.status = SignupStatus.REJECTED
    signup.save(update_fields=["status", "updated_at"])
    remove_user_from_tournament(signup.event, signup.user)
    _promote_from_waitlist(signup.event)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def confirm_signup(signup):
    """Confirm a signup (e.g., during roll call)."""
    if signup.status != SignupStatus.APPROVED:
        raise ValueError("Only approved signups can be confirmed.")
    signup.status = SignupStatus.CONFIRMED
    signup.save(update_fields=["status", "updated_at"])
    add_user_to_tournament(signup.event, signup.user)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def cancel_signup(signup):
    """Cancel a signup."""
    if signup.status in [SignupStatus.CANCELLED, SignupStatus.REJECTED]:
        raise ValueError(f"Cannot cancel signup in '{signup.status}' status.")
    signup.status = SignupStatus.CANCELLED
    signup.save(update_fields=["status", "updated_at"])
    remove_user_from_tournament(signup.event, signup.user)
    _promote_from_waitlist(signup.event)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


def _promote_from_waitlist(event):
    """Promote the next waitlisted user when a slot opens."""
    if not event.max_players:
        return
    if _get_active_signup_count(event) >= event.max_players:
        return
    next_waitlisted = (
        EventSignup.objects.filter(event=event, status=SignupStatus.WAITLISTED)
        .order_by("waitlist_position")
        .first()
    )
    if next_waitlisted:
        next_waitlisted.waitlist_position = None
        if event.auto_approve and check_requirements(event, next_waitlisted.user):
            next_waitlisted.status = SignupStatus.APPROVED
            if event.auto_confirm:
                next_waitlisted.status = SignupStatus.CONFIRMED
                add_user_to_tournament(event, next_waitlisted.user)
            elif not event.roll_call_enabled:
                add_user_to_tournament(event, next_waitlisted.user)
        elif event.auto_approve:
            next_waitlisted.status = SignupStatus.PENDING_APPROVAL
        else:
            next_waitlisted.status = SignupStatus.RSVP
        next_waitlisted.save(
            update_fields=["status", "waitlist_position", "updated_at"]
        )
        invalidate_after_commit(next_waitlisted)


@transaction.atomic
def unconfirm_signup(signup):
    """Revert a confirmed signup back to approved (e.g., during roll call adjustments)."""
    if signup.status != SignupStatus.CONFIRMED:
        raise ValueError("Only confirmed signups can be unconfirmed.")
    signup.status = SignupStatus.APPROVED
    signup.save(update_fields=["status", "updated_at"])
    remove_user_from_tournament(signup.event, signup.user)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def demote_to_waitlist(signup):
    """Move an active signup to the end of the waitlist."""
    if signup.status in [
        SignupStatus.CANCELLED,
        SignupStatus.REJECTED,
        SignupStatus.WAITLISTED,
    ]:
        raise ValueError(f"Cannot demote signup in '{signup.status}' status.")
    max_pos = (
        EventSignup.objects.filter(
            event=signup.event, status=SignupStatus.WAITLISTED
        ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]
        or 0
    )
    signup.status = SignupStatus.WAITLISTED
    signup.waitlist_position = max_pos + 1
    signup.save(update_fields=["status", "waitlist_position", "updated_at"])
    remove_user_from_tournament(signup.event, signup.user)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def reinstate_signup(signup):
    """Reinstate a cancelled signup back to RSVP status."""
    if signup.status != SignupStatus.CANCELLED:
        raise ValueError("Only cancelled signups can be reinstated.")
    event = signup.event
    # Check if event is still accepting signups
    if event.state != "signups_open":
        raise ValueError("Event is not accepting signups.")
    # Check capacity — if full, go to waitlist
    active_count = _get_active_signup_count(event)
    if event.max_players and active_count >= event.max_players:
        max_pos = (
            EventSignup.objects.filter(
                event=event, status=SignupStatus.WAITLISTED
            ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]
            or 0
        )
        signup.status = SignupStatus.WAITLISTED
        signup.waitlist_position = max_pos + 1
    else:
        signup.status = SignupStatus.RSVP
        signup.waitlist_position = None
    signup.save(update_fields=["status", "waitlist_position", "updated_at"])
    invalidate_after_commit(signup, event)
    transaction.on_commit(lambda: notify_signup_changed(event))
    return signup


# ---------------------------------------------------------------------------
# Tournament lifecycle
# ---------------------------------------------------------------------------

LOBBY_CONFIG_FIELDS = [
    "game_mode",
    "custom_game_name",
    "captains_draft_time",
    "lobby_steam_league_id",
]

DISCORD_TOURNAMENT_CONFIG_FIELDS = [
    "auto_create_hero_drafts",
    "discord_send_draft_link",
    "discord_send_herodraft_link",
]


@transaction.atomic
def create_tournament_for_event(event):
    """Create a future Tournament from event template fields. Returns Tournament."""
    tournament = Tournament.objects.create(
        name=event.tournament_name,
        league=event.tournament_league,
        tournament_type=event.tournament_type,
        game_type=event.game_type,
        draft_type=event.draft_type,
        people_per_team=event.people_per_team,
        number_of_teams=event.number_of_teams,
        date_played=event.tournament_date or event.scheduled_at,
        timezone=event.timezone,
        game_mode=event.game_mode,
        custom_game_name=event.custom_game_name,
        captains_draft_time=event.captains_draft_time,
        lobby_steam_league_id=event.lobby_steam_league_id,
        auto_create_hero_drafts=event.auto_create_hero_drafts,
        discord_send_draft_link=event.discord_send_draft_link,
        discord_send_herodraft_link=event.discord_send_herodraft_link,
        state="future",
    )
    event.tournament = tournament
    event.save(update_fields=["tournament", "updated_at"])
    invalidate_after_commit(event)
    return tournament


def ensure_discord_event(event):
    """Auto-create a DiscordEvent row if the org has a discord_server_id.

    This ensures the Discord tab works immediately after event creation
    without waiting for celery tasks to run.
    """
    org = event.organization
    if not org or not org.discord_server_id:
        return None
    from discordbot.models import DiscordEvent

    de, created = DiscordEvent.objects.get_or_create(
        event=event,
        defaults={"guild_id": org.discord_server_id},
    )
    if created:
        logger.info(
            "Auto-created DiscordEvent for event %s (guild=%s)",
            event.pk,
            org.discord_server_id,
        )
    return de


def add_user_to_tournament(event, user):
    """Add a user to the event's linked future tournament."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.users.add(user)
        invalidate_obj(event.tournament)


def remove_user_from_tournament(event, user):
    """Remove a user from the event's linked future tournament."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.users.remove(user)
        invalidate_obj(event.tournament)


def finalize_event_tournament(event):
    """Transition linked tournament from future to in_progress."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.state = "in_progress"
        event.tournament.save(update_fields=["state"])
        invalidate_obj(event.tournament)


def sync_tournament_from_event(event):
    """Cascade event config changes to linked Tournament.

    Returns dict with 'synced' (bool) and 'warning' (str or None).
    """
    if not event.tournament:
        return {"synced": False, "warning": None}

    state = event.tournament.state
    if state == "future":
        event.tournament.name = event.tournament_name
        event.tournament.league = event.tournament_league
        event.tournament.tournament_type = event.tournament_type
        event.tournament.game_type = event.game_type
        event.tournament.draft_type = event.draft_type
        event.tournament.people_per_team = event.people_per_team
        event.tournament.number_of_teams = event.number_of_teams
        event.tournament.date_played = event.tournament_date or event.scheduled_at
        event.tournament.timezone = event.timezone
        for field in LOBBY_CONFIG_FIELDS + DISCORD_TOURNAMENT_CONFIG_FIELDS:
            setattr(event.tournament, field, getattr(event, field))
        event.tournament.save()
        invalidate_obj(event.tournament)
        return {"synced": True, "warning": None}
    elif state == "in_progress":
        return {
            "synced": False,
            "warning": "Tournament is in progress. Changes were saved to the event but not applied to the active tournament.",
        }
    else:
        return {
            "synced": False,
            "warning": "Tournament has already completed. Changes were saved to the event only.",
        }


@transaction.atomic
def restart_event_tournament(event):
    """Delete existing tournament, create fresh one, re-add confirmed users."""
    if not event.tournament:
        raise ValueError("No tournament to restart.")

    old_tournament = event.tournament
    event.tournament = None
    event.save(update_fields=["tournament", "updated_at"])
    old_tournament.delete()

    tournament = create_tournament_for_event(event)

    confirmed = EventSignup.objects.filter(
        event=event,
        status__in=[SignupStatus.CONFIRMED, SignupStatus.APPROVED],
    ).select_related("user")
    for signup in confirmed:
        tournament.users.add(signup.user)

    event.state = EventState.SIGNUPS_OPEN
    event.save(update_fields=["state", "updated_at"])
    invalidate_after_commit(tournament, event)
    return tournament


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------

TOURNAMENT_TEMPLATE_FIELDS = [
    f.name for f in TournamentTemplateMixin._meta.get_fields() if hasattr(f, "column")
]
EVENT_CONFIG_FIELDS = [
    f.name for f in EventConfigMixin._meta.get_fields() if hasattr(f, "column")
]
DISCORD_CONFIG_FIELDS = [
    f.name for f in DiscordEventConfigMixin._meta.get_fields() if hasattr(f, "column")
]


def _python_weekday(sunday_zero_dow):
    """Convert Sunday=0 day-of-week to Python's datetime.weekday() (Monday=0).

    EventRepeater.day_of_week uses the JS/frontend convention (Sunday=0..Saturday=6)
    to match `DAY_LABELS` in frontend/app/components/events/schemas.ts. Python's
    `date.weekday()` returns Monday=0..Sunday=6, so we shift by one.
    """
    return (sunday_zero_dow - 1) % 7


def _get_next_occurrences(repeater, from_date, to_date):
    """Calculate next occurrence datetimes for a repeater within a date range."""
    tz_info = ZoneInfo(repeater.timezone)
    occurrences = []
    end = to_date
    if repeater.ends_at:
        end = min(end, repeater.ends_at)

    if repeater.frequency == RepeatFrequency.DAILY:
        current = max(from_date, repeater.starts_at)
        while current <= end:
            dt = datetime.datetime.combine(
                current, repeater.time_of_day, tzinfo=tz_info
            )
            occurrences.append(dt)
            current += timedelta(days=1)

    elif repeater.frequency in (
        RepeatFrequency.WEEKLY,
        RepeatFrequency.EVERY_TWO_WEEKS,
    ):
        step = 7 if repeater.frequency == RepeatFrequency.WEEKLY else 14
        target_weekday = _python_weekday(repeater.day_of_week)
        current = max(from_date, repeater.starts_at)
        while current.weekday() != target_weekday:
            current += timedelta(days=1)
        while current <= end:
            dt = datetime.datetime.combine(
                current, repeater.time_of_day, tzinfo=tz_info
            )
            occurrences.append(dt)
            current += timedelta(days=step)

    elif repeater.frequency == RepeatFrequency.MONTHLY:
        target_day = repeater.starts_at.day
        current = max(from_date, repeater.starts_at)
        while current <= end:
            try:
                month_date = current.replace(day=target_day)
            except ValueError:
                last_day = calendar.monthrange(current.year, current.month)[1]
                month_date = current.replace(day=last_day)
            if from_date <= month_date <= end:
                dt = datetime.datetime.combine(
                    month_date, repeater.time_of_day, tzinfo=tz_info
                )
                occurrences.append(dt)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

    return occurrences


def _copy_mixin_fields(source, target, field_names):
    """Copy mixin field values from source to target model instance."""
    for field_name in field_names:
        setattr(target, field_name, getattr(source, field_name))


def _today():
    """Return today's date. Extracted for testability."""
    return datetime.date.today()


def generate_events_for_repeater(repeater):
    """Generate upcoming events for a repeater. Returns list of created Events."""
    if not repeater.is_active:
        return []
    today = _today()
    if repeater.ends_at and repeater.ends_at < today:
        return []

    to_date = today + timedelta(days=repeater.generate_days_ahead)
    occurrences = _get_next_occurrences(repeater, today, to_date)

    created_events = []
    for dt in occurrences:
        if Event.objects.filter(event_repeater=repeater, scheduled_at=dt).exists():
            continue
        event = Event(
            organization=repeater.organization,
            event_repeater=repeater,
            name=repeater.name,
            description=repeater.description,
            scheduled_at=dt,
            state=EventState.UPCOMING,
            created_by=repeater.created_by,
        )
        _copy_mixin_fields(repeater, event, TOURNAMENT_TEMPLATE_FIELDS)
        _copy_mixin_fields(repeater, event, EVENT_CONFIG_FIELDS)
        _copy_mixin_fields(repeater, event, DISCORD_CONFIG_FIELDS)
        event.tournament_date = dt
        event.save()
        create_tournament_for_event(event)
        ensure_discord_event(event)
        created_events.append(event)
        # PR-1: announcement is scheduled (fires discord_announcement_hours
        # before scheduled_at via the registry). Legacy notify_event_announced
        # immediate-dispatch removed.
        if repeater.discord_notify_new_events:
            notify_new_event(event)
        if event.discord_create_event:
            from events.discord import notify_create_discord_event

            notify_create_discord_event(event)
    return created_events


@transaction.atomic
def sync_future_events(repeater):
    """Propagate repeater changes to all upcoming events in the series.

    Only updates events that haven't progressed past 'upcoming' state
    (i.e. signups haven't opened yet), so in-progress events are untouched.
    """
    future_events = Event.objects.filter(
        event_repeater=repeater,
        state=EventState.UPCOMING,
    ).select_related("tournament")
    shared_fields = ["name", "description"]
    update_fields = (
        shared_fields
        + TOURNAMENT_TEMPLATE_FIELDS
        + EVENT_CONFIG_FIELDS
        + DISCORD_CONFIG_FIELDS
    )
    updated = 0
    for event in future_events:
        for field_name in shared_fields:
            setattr(event, field_name, getattr(repeater, field_name))
        _copy_mixin_fields(repeater, event, TOURNAMENT_TEMPLATE_FIELDS)
        _copy_mixin_fields(repeater, event, EVENT_CONFIG_FIELDS)
        _copy_mixin_fields(repeater, event, DISCORD_CONFIG_FIELDS)
        event.tournament_date = event.scheduled_at
        event.save(update_fields=update_fields + ["tournament_date", "updated_at"])
        sync_tournament_from_event(event)
        updated += 1
    logger.info("Synced %d upcoming events for repeater %s", updated, repeater.pk)
    return updated
