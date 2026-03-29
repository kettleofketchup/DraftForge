"""Embed builders for tournament Discord DM notifications.

All functions accept primitive values (str, int) so they work
regardless of whether the caller has Django models or Pydantic objects.
"""

from django.conf import settings

LOGO_URL = "https://assets.kettle.sh/draftforge/DFLogo.png"
COLOR_DRAFT = 0x5865F2
COLOR_HERODRAFT = 0xED4245


def _dflogo_emoji():
    """Get the DraftForge application emoji for button components.
    Returns emoji dict if DFLOGO_EMOJI_ID is configured, else None.
    """
    emoji_id = getattr(settings, "DFLOGO_EMOJI_ID", None)
    if not emoji_id:
        return None
    return {"name": "dflogo", "id": str(emoji_id)}


def _site_url():
    return getattr(settings, "SITE_URL", "") or "https://localhost"


def build_draft_link_embed(
    tournament_name, draft_type_display, tournament_id, date_played=None
):
    """Rich embed for team draft start DM."""
    url = f"{_site_url()}/tournament/{tournament_id}/teams/draft"
    fields = [{"name": "Draft Type", "value": draft_type_display, "inline": True}]
    if date_played:
        fields.append(
            {
                "name": "Date / Time",
                "value": f"<t:{int(date_played.timestamp())}:F>",
                "inline": True,
            }
        )
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Team Draft Started",
        "description": (
            f"The team draft for **[{tournament_name}]({url})** has begun!\n\n"
            f"Click the button below to view the draft."
        ),
        "color": COLOR_DRAFT,
        "fields": fields,
        "url": url,
    }


def build_draft_link_components(tournament_id):
    """Link button to view team draft."""
    btn = {
        "type": 2,
        "style": 5,
        "label": "Open in Browser",
        "url": f"{_site_url()}/tournament/{tournament_id}/teams/draft",
    }
    emoji = _dflogo_emoji()
    if emoji:
        btn["emoji"] = emoji
    return [{"type": 1, "components": [btn]}]


def build_herodraft_link_embed(tournament_name, herodraft_pk, radiant_name, dire_name):
    """Rich embed for hero draft creation DM."""
    url = f"{_site_url()}/herodraft/{herodraft_pk}"
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Hero Draft Ready",
        "description": (
            f"A hero draft has been created for **[{tournament_name}]({url})**!\n\n"
            f"**{radiant_name}** vs **{dire_name}**\n\n"
            f"Click the button below to join."
        ),
        "color": COLOR_HERODRAFT,
        "url": url,
    }


def build_herodraft_link_components(herodraft_pk):
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
    return [{"type": 1, "components": [btn]}]
