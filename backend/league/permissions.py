"""League permission helpers."""

from collections.abc import Mapping
from typing import Any

from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions
from rest_framework.request import Request

from app.models import CustomUser, League
from league.models import LeagueUser
from org.permissions import (
    _payload_lists_user,
    can_view_org_members,
    has_org_admin_access,
    has_org_staff_access,
)


def has_league_admin_access(user: CustomUser | AnonymousUser, league: League) -> bool:
    """Check if user is league admin, admin of the league's org, or site admin."""
    if not user.is_authenticated:
        return False

    # Site admin (Django is_staff OR is_superuser) bypasses the cascade —
    # matches the frontend permission-hook convention so the matrix
    # contract holds end-to-end.
    if user.is_staff or user.is_superuser:
        return True

    if league.admins.filter(pk=user.pk).exists():
        return True

    # Check if user is admin (or owner) of the linked organization
    if league.organization and has_org_admin_access(user, league.organization):
        return True

    return False


def has_league_staff_access(user: CustomUser | AnonymousUser, league: League) -> bool:
    """Check if user has staff access to league."""
    if not user.is_authenticated:
        return False

    if has_league_admin_access(user, league):
        return True

    if league.staff.filter(pk=user.pk).exists():
        return True

    if league.organization and has_org_staff_access(user, league.organization):
        return True

    return False


def _is_league_member(user: CustomUser, league_pk: int) -> bool:
    return (
        LeagueUser.objects.nocache()
        .filter(league_id=league_pk, user_id=user.pk)
        .exists()
    )


def can_view_league_members(user: CustomUser | AnonymousUser, league: League) -> bool:
    """Whoever may view the linked org's members, plus the league's own members even
    when the org list is private; league staff and members for org-less leagues."""
    if not user.is_authenticated:
        return False
    if league.organization_id is not None:
        if can_view_org_members(user, league.organization_id):
            return True
    elif has_league_staff_access(user, league):
        return True
    return _is_league_member(user, league.pk)


def can_view_league_members_from_payload(
    user: CustomUser | AnonymousUser, data: Mapping[str, Any]
) -> bool:
    """can_view_league_members for a serialized LeagueSerializer payload."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser or _payload_lists_user(user, data):
        return True
    organization = data.get("organization")
    if isinstance(organization, Mapping) and can_view_org_members(
        user, organization["pk"]
    ):
        return True
    return _is_league_member(user, data["pk"])


class IsLeagueAdmin(permissions.BasePermission):
    """Permission check for league admin access."""

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return has_league_admin_access(request.user, obj)
