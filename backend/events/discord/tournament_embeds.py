"""Embed builders for tournament Discord DM notifications.

All functions accept primitive values (str, int) so they work
regardless of whether the caller has Django models or Pydantic objects.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from app.constants import LOGO_URL

COLOR_DRAFT = 0x5865F2
COLOR_HERODRAFT = 0xED4245


def _dflogo_emoji() -> dict[str, str] | None:
    """Get the DraftForge application emoji for button components.
    Returns emoji dict if DFLOGO_EMOJI_ID is configured, else None.
    """
    emoji_id = getattr(settings, "DFLOGO_EMOJI_ID", None)
    if not emoji_id:
        return None
    return {"name": "dflogo", "id": str(emoji_id)}


def _site_url() -> str:
    return getattr(settings, "SITE_URL", "") or "https://localhost"


def build_draft_link_embed(
    tournament_name: str,
    draft_type_display: str,
    tournament_id: int,
    date_played: datetime | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Rich embed for team draft start DM."""
    url = f"{_site_url()}/tournament/{tournament_id}/teams/draft"
    fields = [{"name": "Draft Type", "value": draft_type_display, "inline": True}]
    if date_played:
        when_value = f"<t:{int(date_played.timestamp())}:F>"
        if timezone:
            local_dt = date_played.astimezone(ZoneInfo(timezone))
            when_value += f" ({local_dt.strftime('%-I:%M %p %Z')})"
        fields.append({"name": "Date / Time", "value": when_value, "inline": True})
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Team Draft Started",
        "description": (
            f"The team draft for **[{tournament_name}]({url})** has begun!\n\n"
            f"{_draft_instructions()}"
        ),
        "color": COLOR_DRAFT,
        "fields": fields,
        "url": url,
    }


def build_draft_link_components(
    tournament_id: int, *, draft_id: int | None = None
) -> list[dict]:
    """Browser link and optional Activity launcher for the specific team draft."""
    btn = {
        "type": 2,
        "style": 5,
        "label": "Open in Browser",
        "url": f"{_site_url()}/tournament/{tournament_id}/teams/draft",
    }
    emoji = _dflogo_emoji()
    if emoji:
        btn["emoji"] = emoji
    return _draft_buttons(btn, "team", draft_id)


def build_herodraft_link_embed(
    tournament_name: str, herodraft_pk: int, radiant_name: str, dire_name: str
) -> dict[str, Any]:
    """Rich embed for hero draft creation DM."""
    url = f"{_site_url()}/herodraft/{herodraft_pk}"
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Hero Draft Ready",
        "description": (
            f"A hero draft has been created for **[{tournament_name}]({url})**!\n\n"
            f"**{radiant_name}** vs **{dire_name}**\n\n"
            f"{_draft_instructions()}"
        ),
        "color": COLOR_HERODRAFT,
        "url": url,
    }


def build_herodraft_link_components(herodraft_pk: int) -> list[dict]:
    """Link button to join hero draft."""
    btn = {
        "type": 2,
        "style": 5,
        "label": "Open in Browser",
        "url": f"{_site_url()}/herodraft/{herodraft_pk}",
    }
    emoji = _dflogo_emoji()
    if emoji:
        btn["emoji"] = emoji
    return _draft_buttons(btn, "hero", herodraft_pk)


def _draft_buttons(browser_button: dict, kind: str, draft_id: int | None) -> list[dict]:
    buttons = [browser_button]
    if getattr(settings, "DISCORD_ACTIVITY_ENABLED", False) and draft_id:
        buttons.append(
            {
                "type": 2,
                "style": 1,
                "label": "Launch / Join Activity",
                "custom_id": f"draft_activity:{kind}:{draft_id}",
            }
        )
    return [{"type": 1, "components": buttons}]


def _draft_instructions() -> str:
    if getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return (
            "Join your team's voice channel, then click **Launch / Join Activity** "
            "to get an invite for this draft in that channel. "
            "Open the invite to launch or join DraftForge. "
            "You can also use **Open in Browser**."
        )
    return "Click the button below to view the draft."


COLOR_LOBBY = 0x57F287


def build_lobby_info_embed(
    tournament_name: str,
    *,
    lobby_name: str,
    password: str,
    side: str,
    team_name: str,
    matchup: str,
    region: str = "",
) -> dict:
    """Rich embed for the in-game lobby DM: where to join and on which side.

    Carries the lobby password, so callers must not log it or store it
    (send it without a tournament_log_id).
    """
    fields = [
        {"name": "Lobby", "value": lobby_name or "-", "inline": False},
        {
            "name": "Password",
            "value": f"||{password}||" if password else "(none)",
            "inline": True,
        },
        {"name": "Your side", "value": f"{side.title()} ({team_name})", "inline": True},
    ]
    if region:
        fields.append({"name": "Region", "value": region, "inline": True})
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Your Dota 2 Lobby Is Ready",
        "description": (
            f"**{tournament_name}**: **{matchup}**\n\n"
            "Accept the lobby invite in Dota 2, or join from the custom lobby "
            "browser with the password below."
        ),
        "color": COLOR_LOBBY,
        "fields": fields,
    }
