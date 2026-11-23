"""Event permission helpers."""

from typing import Any

from django.contrib.auth.models import AnonymousUser

from app.models import CustomUser
from league.permissions import has_league_staff_access
from org.permissions import has_org_staff_access


def has_event_staff_access(user: CustomUser | AnonymousUser | None, event: Any) -> bool:
    """Org staff for event.organization, or league staff for event.tournament_league."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if has_org_staff_access(user, event.organization):
        return True
    if event.tournament_league_id and has_league_staff_access(
        user, event.tournament_league
    ):
        return True
    return False
