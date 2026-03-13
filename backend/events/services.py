import calendar
import datetime
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from cacheops import invalidate_obj
from django.db import transaction

from app.models import Tournament
from events.models import (
    Event,
    EventConfigMixin,
    EventSignup,
    EventState,
    RepeatFrequency,
    SignupStatus,
    SignupType,
    TournamentTemplateMixin,
)

logger = logging.getLogger(__name__)


def check_requirements(event, user):
    """Check if user meets event confirmation requirements."""
    if event.require_steam_id and not user.steamid:
        return False
    if event.require_mmr_verified and not user.has_active_dota_mmr:
        return False
    if event.require_profile_complete:
        if not user.nickname or not user.steamid or not user.discordId:
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
def process_rsvp(event, user, event_team=None):
    """Process an RSVP for an event."""
    if event.state != EventState.SIGNUPS_OPEN:
        raise ValueError("Event is not accepting signups.")
    if EventSignup.objects.filter(event=event, user=user).exists():
        raise ValueError("User has already signed up for this event.")

    signup_type = SignupType.TEAM if event_team else SignupType.USER

    # Check waitlist
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
        invalidate_obj(event)
        return signup

    # Determine initial status
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
    invalidate_obj(event)
    return signup


APPROVABLE_STATUSES = [SignupStatus.RSVP, SignupStatus.PENDING_APPROVAL]


def approve_signup(signup):
    """Approve a signup."""
    if signup.status not in APPROVABLE_STATUSES:
        raise ValueError(f"Cannot approve signup in '{signup.status}' status.")
    signup.status = SignupStatus.APPROVED
    signup.save(update_fields=["status", "updated_at"])
    invalidate_obj(signup.event)
    return signup


def reject_signup(signup):
    """Reject a signup."""
    if signup.status in [SignupStatus.REJECTED, SignupStatus.CANCELLED]:
        raise ValueError(f"Cannot reject signup in '{signup.status}' status.")
    signup.status = SignupStatus.REJECTED
    signup.save(update_fields=["status", "updated_at"])
    _promote_from_waitlist(signup.event)
    invalidate_obj(signup.event)
    return signup


def confirm_signup(signup):
    """Confirm a signup (e.g., during roll call)."""
    if signup.status != SignupStatus.APPROVED:
        raise ValueError("Only approved signups can be confirmed.")
    signup.status = SignupStatus.CONFIRMED
    signup.save(update_fields=["status", "updated_at"])
    invalidate_obj(signup.event)
    return signup


def cancel_signup(signup):
    """Cancel a signup."""
    if signup.status in [SignupStatus.CANCELLED, SignupStatus.REJECTED]:
        raise ValueError(f"Cannot cancel signup in '{signup.status}' status.")
    signup.status = SignupStatus.CANCELLED
    signup.save(update_fields=["status", "updated_at"])
    _promote_from_waitlist(signup.event)
    invalidate_obj(signup.event)
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
        else:
            next_waitlisted.status = SignupStatus.RSVP
        next_waitlisted.save(
            update_fields=["status", "waitlist_position", "updated_at"]
        )


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------

TOURNAMENT_TEMPLATE_FIELDS = [
    f.name for f in TournamentTemplateMixin._meta.get_fields() if hasattr(f, "column")
]
EVENT_CONFIG_FIELDS = [
    f.name for f in EventConfigMixin._meta.get_fields() if hasattr(f, "column")
]


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
        current = max(from_date, repeater.starts_at)
        while current.weekday() != repeater.day_of_week:
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
        event.tournament_date = dt
        event.save()
        created_events.append(event)
    return created_events


# ---------------------------------------------------------------------------
# Tournament auto-start
# ---------------------------------------------------------------------------


@transaction.atomic
def auto_start_event(event):
    """Auto-start a tournament for an event. Returns Tournament or None.

    No select_for_update -- SQLite doesn't support it. Idempotency via state check.
    """
    if event.state != EventState.SIGNUPS_OPEN:
        return None
    if not event.auto_start:
        return None
    if event.roll_call_enabled:
        return None

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
    )

    confirmed_signups = EventSignup.objects.filter(
        event=event,
        status__in=[SignupStatus.CONFIRMED, SignupStatus.APPROVED],
    ).select_related("user")
    for signup in confirmed_signups:
        tournament.users.add(signup.user)

    event.tournament = tournament
    event.state = EventState.IN_PROGRESS
    event.save(update_fields=["tournament", "state", "updated_at"])
    invalidate_obj(event)
    invalidate_obj(tournament)
    return tournament
