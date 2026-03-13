import logging

from cacheops import invalidate_obj
from django.db import transaction

from events.models import EventSignup, EventState, SignupStatus, SignupType

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
