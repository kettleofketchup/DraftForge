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
