"""Draft target helpers shared by Activity modules; imports no discordbot.activity* module."""

from django.conf import settings

from app.models import Draft, HeroDraft


def draft_tournament_id(draft: HeroDraft | Draft) -> int | None:
    if isinstance(draft, HeroDraft):
        return draft.game.tournament_id
    return draft.tournament_id


def draft_site_url(kind: str, draft: HeroDraft | Draft) -> str:
    if kind == "hero":
        return f"{settings.SITE_URL}/herodraft/{draft.pk}"
    return f"{settings.SITE_URL}/tournament/{draft_tournament_id(draft)}/teams/draft"
