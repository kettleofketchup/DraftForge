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


class SignupType(models.TextChoices):
    USER = "user", "User"
    TEAM = "team", "Team"


class RepeatFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    EVERY_TWO_WEEKS = "every_two_weeks", "Every Two Weeks"
    MONTHLY = "monthly", "Monthly"
