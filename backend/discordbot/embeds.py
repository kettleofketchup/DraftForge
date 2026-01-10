"""Pre-built Discord embed templates."""

from django.conf import settings


def event_announcement_embed(template):
    """Build embed dict from EventTemplate."""
    return {
        "title": template.title,
        "description": template.description,
        "color": int(template.color.lstrip("#"), 16),
        "footer": {"text": "React: \u2705 Yes | \u2753 Maybe | \u274c No"},
    }


def tournament_created_embed(tournament):
    """Rich embed for tournament announcements."""
    embed = {
        "title": f"\U0001f3c6 New Tournament: {tournament.name}",
        "description": "A new tournament has been created!",
        "color": 0x00FF00,
        "fields": [],
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/tournament/{tournament.id}"

    return embed


def draft_ready_embed(draft):
    """Rich embed when draft is ready to start."""
    embed = {
        "title": f"\U0001f4cb Draft Ready: {draft.name}",
        "description": "The draft is ready to begin!",
        "color": 0x5865F2,
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/draft/{draft.id}"

    return embed


def results_posted_embed(tournament):
    """Rich embed for tournament results."""
    embed = {
        "title": f"\U0001f389 Results Posted: {tournament.name}",
        "description": "Check out the final standings!",
        "color": 0xFFD700,
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/tournament/{tournament.id}/results"

    return embed
