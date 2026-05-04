"""
Embed builders for Discord event notifications.

Pure functions that construct embed dicts for the Discord API.
"""

import logging

from django.conf import settings

from app.constants import LOGO_URL
from app.internal_client import get_event_signups

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


INACTIVE_STATUSES = {"cancelled", "rejected", "waitlisted", "tentative"}
DECLINED_STATUSES = {"cancelled", "rejected"}
CONFIRMED_STATUSES = {"confirmed", "approved"}


def _signup_counts(event):
    signups = get_event_signups(event.pk)
    active = [s for s in signups if s.status not in INACTIVE_STATUSES]
    confirmed = [s for s in signups if s.status == "confirmed"]
    return len(active), len(confirmed)


def _user_list(signups, max_items=40):
    """Build a newline-separated list of user display names from signups."""
    lines = []
    for s in signups[:max_items]:
        lines.append(s.display_name)
    remaining = len(signups) - max_items
    if remaining > 0:
        lines.append(f"*and {remaining} more...*")
    return "\n".join(lines) if lines else "*None yet*"


def _user_list_quoted(signups, max_items=40, numbered=True):
    """Build a blockquoted numbered list of user display names from signups."""
    lines = []
    for i, s in enumerate(signups[:max_items], 1):
        name = s.display_name
        if numbered:
            lines.append(f"> {i}. {name}")
        else:
            lines.append(f"> {name}")
    remaining = len(signups) - max_items
    if remaining > 0:
        lines.append(f"> *and {remaining} more...*")
    return "\n".join(lines) if lines else "> *—*"


EMBED_FIELD_VALUE_LIMIT = 1024  # Discord per-field char limit


class _IconStrip:
    """Wraps a signup object with an icon prefix prepended to display_name."""

    def __init__(self, s, icon):
        self._s = s
        self.display_name = f"{icon} {s.display_name}"
        self.status = s.status


def build_user_list_fields(signups, *, name, inline=True, max_items=40, numbered=False):
    """Build one or more embed fields for a signup list.

    Returns a list of {name, value, inline} dicts. Splits into a 'cont.' field
    when the joined line set would exceed Discord's 1024-char per-field limit.
    Empty input returns a single field with '*None yet*'.
    """
    if not signups:
        return [{"name": name, "value": "*None yet*", "inline": inline}]

    capped = signups[:max_items]
    remaining = len(signups) - max_items

    lines = []
    for i, s in enumerate(capped, 1):
        line = f"> {i}. {s.display_name}" if numbered else s.display_name
        lines.append(line)
    if remaining > 0:
        lines.append(f"*and {remaining} more...*")

    fields = []
    bucket: list = []
    bucket_len = 0
    for line in lines:
        added = len(line) + (1 if bucket else 0)  # +1 for "\n" separator
        if bucket_len + added > EMBED_FIELD_VALUE_LIMIT:
            fields.append({
                "name": name if not fields else f"{name} (cont.)",
                "value": "\n".join(bucket),
                "inline": inline,
            })
            bucket = [line]
            bucket_len = len(line)
        else:
            bucket.append(line)
            bucket_len += added

    if bucket:
        fields.append({
            "name": name if not fields else f"{name} (cont.)",
            "value": "\n".join(bucket),
            "inline": inline,
        })
    return fields


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

    # Embed 2: Participants (fetched via public API)
    all_signups = get_event_signups(event.pk)

    active = [s for s in all_signups if s.status not in INACTIVE_STATUSES]
    count = len(active)
    max_display = str(event.max_players) if event.max_players else "\u221e"

    icon_signups = [
        _IconStrip(s, "\u2705" if s.status in CONFIRMED_STATUSES else "\u23f3")
        for s in active
    ]
    participant_fields = build_user_list_fields(
        icon_signups,
        name=f"\u2705 Signed Up ({count}/{max_display})",
        inline=True,
        numbered=False,
    )

    declined = [s for s in all_signups if s.status in DECLINED_STATUSES]
    participant_fields.append(
        {
            "name": f"\u274c Declined ({len(declined)})",
            "value": _user_list(declined),
            "inline": True,
        }
    )

    tentative = [s for s in all_signups if s.status == "tentative"]
    participant_fields.append(
        {
            "name": f"\u2753 Tentative ({len(tentative)})",
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

    # Signup lists (fetched via public API, typed as EventSignupData)
    all_signups = get_event_signups(event.pk)

    # Signed Up
    active = [s for s in all_signups if s.status not in INACTIVE_STATUSES]
    count = len(active)
    max_display = str(event.max_players) if event.max_players else "\u221e"

    class _PendingStrip:
        """Wraps signup with blockquote + pending suffix for non-confirmed."""

        def __init__(self, s, idx):
            self.status = s.status
            if s.status in CONFIRMED_STATUSES:
                self.display_name = f"> {idx}. {s.display_name}"
            else:
                self.display_name = f"> {idx}. *{s.display_name} (pending)*"

    pending_signups = [_PendingStrip(s, i) for i, s in enumerate(active, 1)]
    for field in build_user_list_fields(
        pending_signups,
        name=f"\u2705 Signed Up ({count}/{max_display})",
        inline=True,
        numbered=False,
    ):
        fields.append(field)

    # Declined
    declined = [s for s in all_signups if s.status in DECLINED_STATUSES]
    fields.append(
        {
            "name": f"\u274c Declined ({len(declined)})",
            "value": _user_list_quoted(declined),
            "inline": True,
        }
    )

    # Tentative
    tentative = [s for s in all_signups if s.status == "tentative"]
    fields.append(
        {
            "name": f"\u2753 Tentative ({len(tentative)})",
            "value": _user_list_quoted(tentative),
            "inline": True,
        }
    )

    # Waitlisted
    waitlisted = sorted(
        [s for s in all_signups if s.status == "waitlisted"],
        key=lambda s: s.waitlist_position or 999,
    )
    if waitlisted:
        fields.append(
            {
                "name": f"\U0001f4cb Waitlisted ({len(waitlisted)})",
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
    from zoneinfo import ZoneInfo

    desc = f"A new event has been created for **{event.organization.name}**!"
    if url := _event_url(event):
        desc += f"\n\n[Sign Up]({url})"

    tz = ZoneInfo(event.timezone) if getattr(event, "timezone", None) else None
    local_dt = event.scheduled_at.astimezone(tz) if tz else event.scheduled_at
    tz_time = local_dt.strftime("%-I:%M %p %Z")

    return {
        "title": f"\U0001f195 {event.name}",
        "description": desc,
        "color": COLOR_NEW_EVENT,
        "fields": [
            {
                "name": "When",
                "value": f"{_discord_timestamp(event.scheduled_at)} ({tz_time})",
                "inline": True,
            },
        ],
    }


def _build_reminder_embed(
    event, title, description, color, extra_fields=None, include_buttons=False
):
    """Shared layout for all reminder embeds — matches announcement style.

    Includes: branding (org name + logo), event time, signup count, event page
    link, and optional extra fields.

    Returns dict with 'embed' key always, plus 'components' if include_buttons=True.
    For backwards compat, also has 'title'/'description'/'color' at top level.
    """

    url = _event_url(event)
    active = getattr(event, "signup_count", 0)
    max_display = str(event.max_players) if event.max_players else "\u221e"

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(event.timezone) if getattr(event, "timezone", None) else None
    local_dt = event.scheduled_at.astimezone(tz) if tz else event.scheduled_at
    tz_time = local_dt.strftime("%-I:%M %p %Z")  # "6:00 PM EST"

    fields = [
        {
            "name": "When",
            "value": f"{_discord_timestamp(event.scheduled_at, style='F')}\n{_discord_timestamp(event.scheduled_at, style='R')} ({tz_time})",
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

    # Build components (buttons) if requested
    components = []
    if include_buttons:
        row = {"type": 1, "components": []}

        # Sign Up button
        row["components"].append(
            {
                "type": 2,
                "style": 3,  # Success (green)
                "label": "Sign Up",
                "custom_id": f"event_signup:{event.pk}",
                "emoji": {"name": "\u2705"},
            }
        )

        # View Event link button
        if url:
            row["components"].append(
                {
                    "type": 2,
                    "style": 5,  # Link
                    "label": "View Event",
                    "url": url,
                    "emoji": {"name": "\U0001f310"},
                }
            )

        components.append(row)

    # Return both embed dict and the full result for sync_send_embed_with_components
    result = {
        # Legacy keys for sync_send_embed (title/description/color)
        "title": embed["title"],
        "description": embed["description"],
        "color": embed["color"],
        "fields": embed.get("fields"),
        # Full embed for sync_send_embed_with_components
        "embed": embed,
        "components": components,
    }
    return result


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
        include_buttons=True,
    )


def build_attendance_reminder_embed(event):
    return _build_reminder_embed(
        event,
        title=f"\u270b {event.name} \u2014 Confirm Attendance",
        description="The event is coming up! Please confirm your attendance by reacting to the signup post.",
        color=COLOR_REMINDER,
        include_buttons=True,
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
        include_buttons=True,
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
        include_buttons=True,
    )
