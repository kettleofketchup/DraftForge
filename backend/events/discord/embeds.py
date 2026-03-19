"""
Embed builders for Discord event notifications.

Pure functions that construct embed dicts for the Discord API.
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


def _discord_timestamp(dt, style="F"):
    """Format a datetime as a Discord timestamp. Style: F=full, R=relative, t=time, d=date."""
    return f"<t:{int(dt.timestamp())}:{style}>"


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


def _user_list(signups, max_items=20):
    """Build a newline-separated list of user nicknames from signups."""
    lines = []
    for s in signups[:max_items]:
        name = s.user.nickname or s.user.username or f"User {s.user.pk}"
        lines.append(name)
    remaining = signups.count() - max_items
    if remaining > 0:
        lines.append(f"*and {remaining} more...*")
    return "\n".join(lines) if lines else "*None yet*"


def build_announcement_embed(event):
    """Build embed for event announcement with signup lists."""
    title = event.discord_event_title or event.name
    desc = event.discord_event_description or event.description or "No description."

    if event.discord_event_info:
        desc += f"\n\n{event.discord_event_info}"

    # Top row: When | Max Players | Event Link (all inline)
    fields = [
        {
            "name": "When",
            "value": _discord_timestamp(event.scheduled_at, style="f"),
            "inline": True,
        },
        {
            "name": "Max Players",
            "value": str(event.max_players or "Unlimited"),
            "inline": True,
        },
    ]

    url = _event_url(event)
    if url:
        fields.append(
            {
                "name": "Event Page",
                "value": f"[View on Site]({url})",
                "inline": True,
            }
        )

    # Bottom row: Signed Up | Declined | Tentative (all inline, always shown)
    signups = EventSignup.objects.filter(event=event).select_related("user")

    # Signed Up: confirmed/approved (✅) + pending (⏳)
    active = signups.exclude(
        status__in=[
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.WAITLISTED,
            SignupStatus.TENTATIVE,
        ]
    )
    active_lines = []
    for s in active[:20]:
        icon = (
            "\u2705"
            if s.status in (SignupStatus.CONFIRMED, SignupStatus.APPROVED)
            else "\u23f3"
        )
        name = s.user.nickname or s.user.username or f"User {s.user.pk}"
        active_lines.append(f"{icon} {name}")
    if active.count() > 20:
        active_lines.append(f"*and {active.count() - 20} more...*")
    count = active.count()
    max_display = str(event.max_players) if event.max_players else "\u221e"
    fields.append(
        {
            "name": f"\u2705 Signed Up ({count}/{max_display})",
            "value": "\n".join(active_lines) if active_lines else "*None yet*",
            "inline": True,
        }
    )

    # Declined
    declined = signups.filter(
        status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED]
    )
    fields.append(
        {
            "name": f"\u274c Declined ({declined.count()})",
            "value": _user_list(declined),
            "inline": True,
        }
    )

    # Tentative
    tentative = signups.filter(status=SignupStatus.TENTATIVE)
    fields.append(
        {
            "name": f"\u2753 Tentative ({tentative.count()})",
            "value": _user_list(tentative),
            "inline": True,
        }
    )

    return {
        "title": f"\U0001f4e2 {title}",
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "fields": fields,
        "timestamp": event.scheduled_at.isoformat(),
    }


def build_signup_update_embed(event):
    active, confirmed = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "\u221e"
    return {
        "title": f"\U0001f4cb {event.name} \u2014 Signups",
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
        "title": f"\U0001f195 {event.name}",
        "description": desc,
        "color": COLOR_NEW_EVENT,
        "fields": [
            {
                "name": "When",
                "value": _discord_timestamp(event.scheduled_at),
                "inline": True,
            },
        ],
    }


def build_signup_reminder_embed(event):
    active, _ = _signup_counts(event)
    max_display = str(event.max_players) if event.max_players else "\u221e"
    return {
        "title": f"\u23f0 {event.name} \u2014 Signup Reminder",
        "description": f"Don't forget to sign up! Currently **{active}/{max_display}** players.",
        "color": COLOR_REMINDER,
    }


def build_attendance_reminder_embed(event):
    return {
        "title": f"\u270b {event.name} \u2014 Confirm Attendance",
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
        "title": f"\U0001f464 {event.name} \u2014 Complete Your Profile",
        "description": f"Please make sure you have: {req_text}",
        "color": COLOR_PROFILE,
    }
