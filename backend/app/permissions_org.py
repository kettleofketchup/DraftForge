"""Organization and League permission helpers."""

from rest_framework import permissions


def is_org_owner(user, organization):
    """Check if user is the org owner."""
    if not user.is_authenticated:
        return False
    return organization.owner_id == user.pk


def has_org_admin_access(user, organization):
    """Check if user is org owner, org admin, or superuser."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or is_org_owner(user, organization)
        or organization.admins.filter(pk=user.pk).exists()
    )


def has_org_staff_access(user, organization):
    """Check if user has staff access to org (owner, admin, or staff)."""
    if not user.is_authenticated:
        return False
    return (
        has_org_admin_access(user, organization)
        or organization.staff.filter(pk=user.pk).exists()
    )


def has_league_admin_access(user, league):
    """Check if user is league admin, admin of any linked org, or superuser."""
    if not user.is_authenticated:
        return False

    # Superuser has access
    if user.is_superuser:
        return True

    # Check if user is a league-specific admin
    if league.admins.filter(pk=user.pk).exists():
        return True

    # Check if user is admin (or owner) of ANY linked organization
    for org in league.organizations.all():
        if has_org_admin_access(user, org):
            return True

    return False


def has_league_staff_access(user, league):
    """Check if user has staff access to league."""
    if not user.is_authenticated:
        return False

    # League admin has staff access
    if has_league_admin_access(user, league):
        return True

    # Check if user is a league-specific staff
    if league.staff.filter(pk=user.pk).exists():
        return True

    # Check if user is staff of ANY linked organization
    for org in league.organizations.all():
        if has_org_staff_access(user, org):
            return True

    return False


class IsOrgOwner(permissions.BasePermission):
    """Permission check for organization owner access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return is_org_owner(request.user, obj) or request.user.is_superuser


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


class IsLeagueStaff(permissions.BasePermission):
    """Permission check for league staff access."""

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return has_league_staff_access(request.user, obj)


# Tournament and Game level permission helpers


def can_edit_tournament(user, tournament):
    """
    Check if user can edit a tournament.

    Requires league admin access (if tournament has a league).

    Args:
        user: The user to check
        tournament: The Tournament instance

    Returns:
        bool: True if user can edit the tournament
    """
    if not user.is_authenticated:
        return False

    # Superuser can edit anything
    if user.is_superuser or user.is_staff:
        return True

    # If tournament has a league, check league admin access
    if tournament.league:
        return has_league_admin_access(user, tournament.league)

    # No league - fall back to org admin if we can find the org
    # This shouldn't normally happen but provides a fallback
    return False


def can_manage_game(user, game):
    """
    Check if user can manage a game (declare winner, link steam match).

    Requires league staff access.

    Args:
        user: The user to check
        game: The Game instance

    Returns:
        bool: True if user can manage the game
    """
    if not user.is_authenticated:
        return False

    # Superuser can manage anything
    if user.is_superuser or user.is_staff:
        return True

    # Check game's league first (direct league reference)
    if game.league:
        return has_league_staff_access(user, game.league)

    # Fall back to tournament's league
    if game.tournament and game.tournament.league:
        return has_league_staff_access(user, game.tournament.league)

    return False


class CanEditTournament(permissions.BasePermission):
    """Permission check for tournament editing."""

    message = "You do not have permission to edit this tournament."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return can_edit_tournament(request.user, obj)


class CanManageGame(permissions.BasePermission):
    """Permission check for game management (declare winner, link steam match)."""

    message = "You do not have permission to manage this game."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return can_manage_game(request.user, obj)
