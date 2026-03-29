"""Embed builders for tournament Discord DM notifications.

All functions accept primitive values (str, int) so they work
regardless of whether the caller has Django models or Pydantic objects.
"""

from django.conf import settings

LOGO_URL = "https://assets.kettle.sh/draftforge/DFLogo.png"
COLOR_DRAFT = 0x5865F2
COLOR_HERODRAFT = 0xED4245


def _site_url():
    return getattr(settings, "SITE_URL", "") or "https://localhost"


def build_draft_link_embed(tournament_name, draft_type_display, draft_pk):
    """Rich embed for team draft start DM."""
    url = f"{_site_url()}/draft/{draft_pk}"
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Team Draft Started",
        "description": f"The team draft for **{tournament_name}** has begun!",
        "color": COLOR_DRAFT,
        "fields": [{"name": "Draft Type", "value": draft_type_display, "inline": True}],
        "url": url,
    }


def build_draft_link_components(draft_pk):
    """Link button to join team draft."""
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 5,
                    "label": "Join Draft",
                    "url": f"{_site_url()}/draft/{draft_pk}",
                }
            ],
        }
    ]


def build_herodraft_link_embed(tournament_name, herodraft_pk, radiant_name, dire_name):
    """Rich embed for hero draft creation DM."""
    url = f"{_site_url()}/herodraft/{herodraft_pk}"
    return {
        "author": {"name": "DraftForge", "icon_url": LOGO_URL},
        "thumbnail": {"url": LOGO_URL},
        "title": "Hero Draft Ready",
        "description": f"A hero draft has been created for **{tournament_name}**!",
        "color": COLOR_HERODRAFT,
        "fields": [
            {"name": "Match", "value": f"{radiant_name} vs {dire_name}", "inline": True}
        ],
        "url": url,
    }


def build_herodraft_link_components(herodraft_pk):
    """Link button to join hero draft."""
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 5,
                    "label": "Join Hero Draft",
                    "url": f"{_site_url()}/herodraft/{herodraft_pk}",
                }
            ],
        }
    ]
