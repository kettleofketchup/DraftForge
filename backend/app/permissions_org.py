"""Organization and League permission helpers."""

from rest_framework import permissions


def has_org_admin_access(user, organization):
    """Check if user is org admin or superuser."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or organization.admins.filter(pk=user.pk).exists()


def has_org_staff_access(user, organization):
    """Check if user has staff access to org (admin or staff)."""
    if not user.is_authenticated:
        return False
    return (
        has_org_admin_access(user, organization)
        or organization.staff.filter(pk=user.pk).exists()
    )


def has_league_admin_access(user, league):
    """Check if user is league admin, org admin, or superuser."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or league.organization.admins.filter(pk=user.pk).exists()
        or league.admins.filter(pk=user.pk).exists()
    )


def has_league_staff_access(user, league):
    """Check if user has staff access to league."""
    if not user.is_authenticated:
        return False
    return (
        has_league_admin_access(user, league)
        or league.organization.staff.filter(pk=user.pk).exists()
        or league.staff.filter(pk=user.pk).exists()
    )


class IsOrgAdmin(permissions.BasePermission):
    """Permission check for organization admin access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return has_org_admin_access(request.user, obj)


class IsLeagueAdmin(permissions.BasePermission):
    """Permission check for league admin access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return has_league_admin_access(request.user, obj)
