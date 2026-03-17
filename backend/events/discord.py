"""
Event <-> Discord integration layer.

Embed builders (pure functions) and dispatch functions that check config flags
and send Celery tasks for Discord notifications.
"""

import logging

from django.conf import settings

from events.models import EventSignup, SignupStatus

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, "SITE_URL", "")

# Colors
COLOR_ANNOUNCEMENT = 0x5865F2  # Discord blurple
COLOR_SIGNUP = 0x57F287  # Green
COLOR_REMINDER = 0xFEE75C  # Yellow
COLOR_PROFILE = 0xEB459E  # Fuchsia
COLOR_NEW_EVENT = 0x00B0F4  # Cyan


def _event_url(event):
    return (
        f"{SITE_URL}/org/{event.organization_id}/events/{event.pk}" if SITE_URL else ""
    )


def _signup_counts(event):
    signups = EventSignup.objects.filter(event=event)
    active = signups.exclude(
        status__in=[
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.WAITLISTED,
        ]
    ).count()
    confirmed = signups.filter(status=SignupStatus.CONFIRMED).count()
    return active, confirmed


def build_announcement_embed(event):
    desc = event.description or "No description."
    if url := _event_url(event):
        desc += f"\n\n[View Event]({url})"
    return {
        "title": f"📢 {event.name}",
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "fields": [
            {
                "name": "When",
                "value": event.scheduled_at.strftime("%A, %B %d at %I:%M %p %Z"),
                "inline": True,
            },
            {
                "name": "Max Players",
                "value": str(event.max_players or "Unlimited"),
                "inline": True,
            },
        ],
    }


def build_signup_update_embed(event):
    active, confirmed = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
    return {
        "title": f"📋 {event.name} — Signups",
        "description": f"Players: **{active}/{max_display}**",
        "color": COLOR_SIGNUP,
        "fields": [
            {"name": "Signed Up", "value": str(active), "inline": True},
            {"name": "Confirmed", "value": str(confirmed), "inline": True},
        ],
    }


def build_new_event_embed(event):
    desc = f"A new event has been created for **{event.organization.name}**!"
    if url := _event_url(event):
        desc += f"\n\n[Sign Up]({url})"
    return {
        "title": f"🆕 {event.name}",
        "description": desc,
        "color": COLOR_NEW_EVENT,
        "fields": [
            {
                "name": "When",
                "value": event.scheduled_at.strftime("%A, %B %d at %I:%M %p %Z"),
                "inline": True,
            },
        ],
    }


def build_signup_reminder_embed(event):
    active, _ = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "∞"
    return {
        "title": f"⏰ {event.name} — Signup Reminder",
        "description": f"Don't forget to sign up! Currently **{active}/{max_display}** players.",
        "color": COLOR_REMINDER,
    }


def build_attendance_reminder_embed(event):
    return {
        "title": f"✋ {event.name} — Confirm Attendance",
        "description": "The event is coming up! Please confirm your attendance.",
        "color": COLOR_REMINDER,
    }


def build_profile_reminder_embed(event):
    requirements = []
    if event.require_steam_id:
        requirements.append("Steam ID")
    if event.require_mmr_verified:
        requirements.append("Verified MMR")
    if event.require_profile_complete:
        requirements.append("Complete profile")
    req_text = ", ".join(requirements) if requirements else "a complete profile"
    return {
        "title": f"👤 {event.name} — Complete Your Profile",
        "description": f"Please make sure you have: {req_text}",
        "color": COLOR_PROFILE,
    }
