"""Who may see and vouch for a member's Steam Friend ID."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from django.contrib.auth.models import AnonymousUser
from django.db.models import OuterRef, QuerySet, Subquery

from app.models import CustomUser
from app.permissions_tournament import has_event_staff_access
from events.constants import SignupStatus
from events.models import Event, EventSignup

VOUCH_EXCLUDED_STATUSES: Final[tuple[str, ...]] = (
    SignupStatus.CANCELLED,
    SignupStatus.REJECTED,
)


@dataclass(frozen=True)
class VerifyGrant:
    org_id: int | None


def _self_signups(target: CustomUser) -> QuerySet[EventSignup]:
    return EventSignup.objects.filter(user_id=target.pk, self_made=True).exclude(
        status__in=VOUCH_EXCLUDED_STATUSES
    )


def self_signup_events(target: CustomUser) -> QuerySet[Event]:
    """Events the target signed up to themselves, most recent signup first."""
    signups = _self_signups(target)
    signed_up_at = Subquery(
        signups.filter(event_id=OuterRef("pk"))
        .order_by("-signed_up_at")
        .values("signed_up_at")[:1]
    )
    return (
        Event.objects.filter(pk__in=signups.values("event_id"))
        .annotate(self_signed_up_at=signed_up_at)
        .select_related("organization", "tournament_league")
        .order_by("-self_signed_up_at", "-pk")
        .distinct()
    )


def _is_site_staff(user: CustomUser) -> bool:
    return bool(user.is_staff or user.is_superuser)


def can_verify_steam_account(
    actor: CustomUser | AnonymousUser | None, target: CustomUser
) -> VerifyGrant | None:
    if actor is None or not actor.is_authenticated:
        return None
    if target.pk is None:
        return VerifyGrant(org_id=None) if _is_site_staff(actor) else None
    if actor.pk == target.pk:
        return None
    if _is_site_staff(actor):
        return VerifyGrant(org_id=None)
    for event in self_signup_events(target):
        if has_event_staff_access(actor, event):
            return VerifyGrant(org_id=event.organization_id)
    return None


def can_view_steam_verification(
    viewer: CustomUser | AnonymousUser | None, target: CustomUser
) -> bool:
    if viewer is None or not viewer.is_authenticated:
        return False
    if _is_site_staff(viewer):
        return True
    return any(has_event_staff_access(viewer, e) for e in self_signup_events(target))
