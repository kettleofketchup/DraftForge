from django.db import models


class EventState(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    SIGNUPS_OPEN = "signups_open", "Signups Open"
    ROLL_CALL = "roll_call", "Roll Call"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


EVENT_STATE_TRANSITIONS = {
    EventState.UPCOMING: [EventState.SIGNUPS_OPEN, EventState.CANCELLED],
    EventState.SIGNUPS_OPEN: [
        EventState.ROLL_CALL,
        EventState.IN_PROGRESS,
        EventState.CANCELLED,
    ],
    EventState.ROLL_CALL: [
        EventState.SIGNUPS_OPEN,
        EventState.IN_PROGRESS,
        EventState.COMPLETED,
        EventState.CANCELLED,
    ],
    EventState.IN_PROGRESS: [EventState.COMPLETED],
    EventState.COMPLETED: [],
    EventState.CANCELLED: [],
}

# Restarting a tournament may also pull a running event back to signups.
EVENT_RESTART_TRANSITIONS = {
    **EVENT_STATE_TRANSITIONS,
    EventState.IN_PROGRESS: [EventState.COMPLETED, EventState.SIGNUPS_OPEN],
}

# Closed events reopen only via events.reopen.reopen_event, which revokes staff points.
EVENT_REOPEN_TRANSITIONS = {
    EventState.COMPLETED: [EventState.SIGNUPS_OPEN],
    EventState.CANCELLED: [EventState.SIGNUPS_OPEN],
}


class SignupStatus(models.TextChoices):
    RSVP = "rsvp", "RSVP"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    CONFIRMED = "confirmed", "Confirmed"
    WAITLISTED = "waitlisted", "Waitlisted"
    TENTATIVE = "tentative", "Tentative"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    DROPPED = "dropped", "Dropped"


SEAT_HOLDING_STATUSES: frozenset[str] = frozenset(
    {
        SignupStatus.RSVP,
        SignupStatus.PENDING_APPROVAL,
        SignupStatus.APPROVED,
        SignupStatus.CONFIRMED,
    }
)

# Signup statuses that put a player in the event's tournament
# (approve_signup / confirm_signup call add_user_to_tournament).
# An allow-list, so DROPPED is excluded on purpose.
REGISTERED_SIGNUP_STATUSES: tuple[str, ...] = (
    SignupStatus.APPROVED,
    SignupStatus.CONFIRMED,
)

# Signups whose stored unmet_requirements follow profile changes.
UNMET_TRACKED_STATUSES: frozenset[str] = frozenset(
    {
        SignupStatus.RSVP,
        SignupStatus.PENDING_APPROVAL,
        SignupStatus.WAITLISTED,
    }
)


class SignupOpenMode(models.TextChoices):
    MANUAL = "manual", "Manual"
    IMMEDIATE = "immediate", "Immediately"
    SCHEDULED = "scheduled", "Hours before start"


class SignupType(models.TextChoices):
    USER = "user", "User"
    TEAM = "team", "Team"


class RepeatFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    EVERY_TWO_WEEKS = "every_two_weeks", "Every Two Weeks"
    MONTHLY = "monthly", "Monthly"


class Commitment(models.TextChoices):
    MAIN = "main", "Main"
    MAYBE = "maybe", "Maybe"


class RsvpClass(models.TextChoices):
    STANDARD = "standard", "Standard"


class ActorRole(models.TextChoices):
    MEMBER = "member"
    STAFF = "staff"
    SYSTEM = "system"


class SignupMeans(models.TextChoices):
    WEB = "web"
    DISCORD_BUTTON = "discord_button"
    DISCORD_REACTION = "discord_reaction"
    SYSTEM = "system"


LINE_EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {SignupStatus.CANCELLED, SignupStatus.REJECTED, SignupStatus.DROPPED}
)


class SignupAction(models.TextChoices):
    BACKFILLED = "backfilled"
    SIGNED_UP = "signed_up"
    RESIGNED_UP = "resigned_up"
    SWITCHED_COMMITMENT = "switched_commitment"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    REJECTED = "rejected"
    WITHDREW = "withdrew"
    DECLINED = "declined"
    WAITLISTED = "waitlisted"
    PROMOTED = "promoted"
    DEMOTED = "demoted"
    REINSTATED = "reinstated"
    VOIDED_WITHDRAWAL = "voided_withdrawal"
    TRANSFERRED_OUT = "transferred_out"
    TRANSFERRED_IN = "transferred_in"
    SWAPPED = "swapped"
    STAFF_ADDED = "staff_added"
    ACCOUNT_MERGED = "account_merged"
    MOVED_EVENT = "moved_event"
    EVENT_CANCELLED = "event_cancelled"
