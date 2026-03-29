"""
Embed builders for Discord event notifications.

Pure functions that construct embed dicts for the Discord API.
"""

import logging

from django.conf import settings

from events.models import EventSignup, SignupStatus

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, "SITE_URL", "") or "https://localhost"

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
    return f"{SITE_URL}/events/{event.pk}" if SITE_URL else ""


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


def _user_list_quoted(signups, max_items=20, numbered=True):
    """Build a blockquoted numbered list of user nicknames from signups."""
    lines = []
    for i, s in enumerate(signups[:max_items], 1):
        name = s.user.nickname or s.user.username or f"User {s.user.pk}"
        if numbered:
            lines.append(f"> {i}. {name}")
        else:
            lines.append(f"> {name}")
    remaining = signups.count() - max_items
    if remaining > 0:
        lines.append(f"> *and {remaining} more...*")
    return "\n".join(lines) if lines else "> *—*"


def build_announcement_embeds(event):
    """Build two embeds for event announcement: info + participants.

    Returns a list of embed dicts (for the Discord API 'embeds' array).
    Embed 1: Event info (title, description, when, max players, link)
    Embed 2: Participants (signed up, declined, tentative)
    """
    title = event.discord_event_title or event.name
    desc = event.discord_event_description or event.description or "No description."

    if event.discord_event_info:
        desc += f"\n\n{event.discord_event_info}"

    # Embed 1: Event info
    info_fields = [
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
        info_fields.append(
            {
                "name": "Event Page",
                "value": f"[View on Site]({url})",
                "inline": True,
            }
        )

    info_embed = {
        "title": title,
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "fields": info_fields,
    }

    # Embed 2: Participants
    signups = EventSignup.objects.filter(event=event).select_related("user")

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

    participant_fields = [
        {
            "name": f"\u2705 Signed Up ({count}/{max_display})",
            "value": "\n".join(active_lines) if active_lines else "*None yet*",
            "inline": True,
        },
    ]

    declined = signups.filter(
        status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED]
    )
    participant_fields.append(
        {
            "name": f"\u274c Declined ({declined.count()})",
            "value": _user_list(declined),
            "inline": True,
        }
    )

    tentative = signups.filter(status=SignupStatus.TENTATIVE)
    participant_fields.append(
        {
            "name": f"\u2753 Tentative ({tentative.count()})",
            "value": _user_list(tentative),
            "inline": True,
        }
    )

    participants_embed = {
        "color": COLOR_ANNOUNCEMENT,
        "fields": participant_fields,
        "timestamp": event.scheduled_at.isoformat(),
    }

    return [info_embed, participants_embed]


def build_announcement_embed(event):
    """Backward-compatible single embed (returns first embed only).

    Use build_announcement_embeds() for the full two-embed layout.
    """
    embeds = build_announcement_embeds(event)
    # Merge into single embed for callers that expect one dict
    combined = embeds[0].copy()
    combined["fields"] = embeds[0]["fields"] + embeds[1]["fields"]
    combined["timestamp"] = embeds[1].get("timestamp")
    return combined


def build_announcement_v2(event):
    """Build embed + components payload for event announcement.

    Returns dict with 'embed' (single embed dict) and 'components' (action rows).
    The embed has: logo thumbnail, title, description, event details row,
    signup/declined/tentative row, and event page link.
    """
    from events.discord.components import build_announcement_components

    LOGO_URL = "https://assets.kettle.sh/draftforge/DFLogo.png"

    title = event.discord_event_title or event.name
    desc = event.discord_event_description or event.description or "No description."

    if event.discord_event_info:
        desc += f"\n\n{event.discord_event_info}"

    # Line 1: Discord date timestamp (renders as "March 20, 2026" in user's locale)
    # Line 2: Discord time timestamp + event timezone time in parentheses
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(event.timezone) if event.timezone else None
    local_dt = event.scheduled_at.astimezone(tz) if tz else event.scheduled_at
    tz_time = local_dt.strftime("%-I:%M %p %Z")  # "6:00 PM EST"

    date_line = local_dt.strftime("%A, %B %-d")  # "Friday, March 20"
    when_value = f"{date_line}\n> {_discord_timestamp(event.scheduled_at, style='t')} ({tz_time})"

    # Top row: When | Max Players | Event Page (all inline)
    fields = [
        {
            "name": "When",
            "value": when_value,
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

    # Force row break — signup fields go on their own row
    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})

    # Signup lists (blockquoted player names)
    signups = EventSignup.objects.filter(event=event).select_related("user")

    # Signed Up
    active = signups.exclude(
        status__in=[
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.WAITLISTED,
            SignupStatus.TENTATIVE,
        ]
    )
    active_lines = []
    for i, s in enumerate(active[:20], 1):
        name = s.user.nickname or s.user.username or f"User {s.user.pk}"
        if s.status in (SignupStatus.CONFIRMED, SignupStatus.APPROVED):
            active_lines.append(f"> {i}. {name}")
        else:
            active_lines.append(f"> {i}. *{name} (pending)*")
    if active.count() > 20:
        active_lines.append(f"> *and {active.count() - 20} more...*")
    count = active.count()
    max_display = str(event.max_players) if event.max_players else "\u221e"
    fields.append(
        {
            "name": f"\u2705 Signed Up ({count}/{max_display})",
            "value": "\n".join(active_lines) if active_lines else "> *None yet*",
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
            "value": _user_list_quoted(declined),
            "inline": True,
        }
    )

    # Tentative
    tentative = signups.filter(status=SignupStatus.TENTATIVE)
    fields.append(
        {
            "name": f"\u2753 Tentative ({tentative.count()})",
            "value": _user_list_quoted(tentative),
            "inline": True,
        }
    )

    # Waitlisted
    waitlisted = signups.filter(status=SignupStatus.WAITLISTED).order_by(
        "waitlist_position"
    )
    if waitlisted.exists():
        fields.append(
            {
                "name": f"\U0001f4cb Waitlisted ({waitlisted.count()})",
                "value": _user_list_quoted(waitlisted),
                "inline": True,
            }
        )

    event_url = f"{SITE_URL}/events/{event.pk}"

    # Embed 1: Title + description + logo thumbnail
    title_embed = {
        "author": {
            "name": "DraftForge",
            "icon_url": LOGO_URL,
            "url": event_url,
        },
        "title": title,
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "thumbnail": {"url": LOGO_URL},
    }

    # Embed 2: Full-width fields + timestamp
    content_embed = {
        "color": COLOR_ANNOUNCEMENT,
        "fields": fields,
        "timestamp": event.scheduled_at.isoformat(),
    }

    components = build_announcement_components(event)

    # Role mentions — go in message content, not in embeds
    signup_role_ids = getattr(event, "discord_signup_role_ids", None) or []
    content = ""
    allowed_mentions = None
    if signup_role_ids:
        mentions = " ".join(f"<@&{rid}>" for rid in signup_role_ids)
        content = mentions
        allowed_mentions = {"roles": [str(rid) for rid in signup_role_ids]}

    result = {"embeds": [title_embed, content_embed], "components": components}
    if content:
        result["content"] = content
    if allowed_mentions:
        result["allowed_mentions"] = allowed_mentions
    return result


def build_announcement_notice(event, signup_link=None):
    """Build a lightweight announcement embed that links to the signup post.

    Posted to the announcement channel to notify users about a new event.
    Not updated — just a one-time heads up.
    """
    LOGO_URL = "https://assets.kettle.sh/draftforge/DFLogo.png"
    title = event.discord_event_title or event.name

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(event.timezone) if event.timezone else None
    local_dt = event.scheduled_at.astimezone(tz) if tz else event.scheduled_at
    date_line = local_dt.strftime("%A, %B %-d")
    time_line = local_dt.strftime("%-I:%M %p %Z")

    desc = f"A new event is coming up!\n\n"
    desc += f"**When:** {date_line} at {time_line}\n"
    desc += f"**Max Players:** {event.max_players or 'Unlimited'}\n"

    if signup_link:
        desc += f"\n\U0001f449 **[Sign up here!]({signup_link})**"

    url = _event_url(event)
    if url:
        desc += f"\n[View on site]({url})"

    event_url = _event_url(event)

    embed = {
        "author": {
            "name": "DraftForge",
            "icon_url": LOGO_URL,
            "url": event_url or signup_link or "",
        },
        "title": f"\U0001f4e2 {title}",
        "description": desc,
        "color": COLOR_ANNOUNCEMENT,
        "thumbnail": {"url": LOGO_URL},
        "timestamp": event.scheduled_at.isoformat(),
    }

    # Role mentions for announcement
    announcement_role_ids = getattr(event, "discord_announcement_role_ids", None) or []
    result = {"embed": embed}
    if announcement_role_ids:
        mentions = " ".join(f"<@&{rid}>" for rid in announcement_role_ids)
        result["content"] = mentions
        result["allowed_mentions"] = {
            "roles": [str(rid) for rid in announcement_role_ids]
        }
    return result


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


def _build_reminder_embed(event, title, description, color, extra_fields=None):
    """Shared layout for all reminder embeds — matches announcement style.

    Includes: branding (org name + logo), event time, signup count, event page
    link, and optional extra fields.
    """
    LOGO_URL = "https://assets.kettle.sh/draftforge/DFLogo.png"

    url = _event_url(event)
    active = getattr(event, "signup_count", 0)
    max_display = str(event.max_players) if event.max_players else "\u221e"

    fields = [
        {
            "name": "When",
            "value": f"{_discord_timestamp(event.scheduled_at, style='F')}\n{_discord_timestamp(event.scheduled_at, style='R')}",
            "inline": True,
        },
        {
            "name": "Signups",
            "value": f"**{active}/{max_display}** players",
            "inline": True,
        },
    ]

    if url:
        fields.append(
            {"name": "Event Page", "value": f"[View & Sign Up]({url})", "inline": True}
        )

    if extra_fields:
        fields.extend(extra_fields)

    embed = {
        "title": title[:256],
        "description": description,
        "color": color,
        "fields": fields,
        "thumbnail": {"url": LOGO_URL},
        "timestamp": event.scheduled_at.isoformat(),
    }

    if hasattr(event, "organization") and event.organization:
        embed["author"] = {"name": event.organization.name}
        if hasattr(event.organization, "logo") and event.organization.logo:
            embed["author"]["icon_url"] = event.organization.logo

    return embed


def build_signup_reminder_embed(event):
    active = getattr(event, "signup_count", 0)
    max_display = str(event.max_players) if event.max_players else "\u221e"
    desc = event.description or ""
    if desc:
        desc = desc[:200] + ("\u2026" if len(desc) > 200 else "")
        desc += "\n\n"
    desc += f"Don't forget to sign up! Currently **{active}/{max_display}** players."
    return _build_reminder_embed(
        event,
        title=f"\u23f0 {event.name} \u2014 Signup Reminder",
        description=desc,
        color=COLOR_REMINDER,
    )


def build_attendance_reminder_embed(event):
    return _build_reminder_embed(
        event,
        title=f"\u270b {event.name} \u2014 Confirm Attendance",
        description="The event is coming up! Please confirm your attendance by reacting to the signup post.",
        color=COLOR_REMINDER,
    )


def build_profile_reminder_embed(event):
    requirements = []
    if getattr(event, "require_steam_id", False):
        requirements.append("Steam ID")
    if getattr(event, "require_mmr_verified", False):
        requirements.append("Verified MMR")
    if getattr(event, "require_profile_complete", False):
        requirements.append("Complete profile")
    req_text = ", ".join(requirements) if requirements else "a complete profile"
    return _build_reminder_embed(
        event,
        title=f"\U0001f464 {event.name} \u2014 Complete Your Profile",
        description=f"Please make sure you have: {req_text}",
        color=COLOR_PROFILE,
    )


def build_subscriber_dm_embed(event):
    """Build DM embed for subscriber pre-event notification.

    Works with both Django model instances and Pydantic EventTaskData.
    """
    desc = f"**{event.name}** is starting soon!"
    if event.description:
        desc += f"\n\n{event.description[:200]}"

    return _build_reminder_embed(
        event,
        title=f"\U0001f514 Event Reminder: {event.name}",
        description=desc,
        color=COLOR_REMINDER,
    )
