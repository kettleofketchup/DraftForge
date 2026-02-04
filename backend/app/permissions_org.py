"""Organization and League permission helpers."""

from rest_framework import permissions


def is_org_owner(user, obj):
    """Check if user is the org owner.

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute
    organization = getattr(obj, "organization", obj)

    return organization.owner_id == user.pk


def has_org_admin_access(user, obj):
    """Check if user is org owner, org admin, or superuser.

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute (e.g., ProfileClaimRequest)
    organization = getattr(obj, "organization", obj)

    return (
        user.is_superuser
        or is_org_owner(user, organization)
        or organization.admins.filter(pk=user.pk).exists()
    )


def has_org_staff_access(user, obj):
    """Check if user has staff access to org (owner, admin, or staff).

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute
    organization = getattr(obj, "organization", obj)

    return (
        has_org_admin_access(user, obj)
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

    # Check if user is admin (or owner) of the linked organization
    if league.organization and has_org_admin_access(user, league.organization):
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

    # Check if user is staff of the linked organization
    if league.organization and has_org_staff_access(user, league.organization):
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

    Checks hierarchy: site admin/staff → org admin/staff → league admin/staff.

    Args:
        user: The user to check
        tournament: The Tournament instance

    Returns:
        bool: True if user can edit the tournament
    """
    if not user.is_authenticated:
        return False

    # Site admin/staff can edit anything
    if user.is_superuser or user.is_staff:
        return True

    # If tournament has a league, check league staff access
    # (which includes org admin/staff through has_league_staff_access)
    if tournament.league:
        return has_league_staff_access(user, tournament.league)

    # No league - fall back to org staff if we can find the org
    if tournament.league and tournament.league.organization:
        return has_org_staff_access(user, tournament.league.organization)

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


class CanEditTeam(permissions.BasePermission):
    """Permission check for team editing via tournament access."""

    message = "You do not have permission to edit this team."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Team belongs to a tournament
        if obj.tournament:
            return can_edit_tournament(request.user, obj.tournament)
        return False


class CanEditDraft(permissions.BasePermission):
    """Permission check for draft editing via tournament access."""

    message = "You do not have permission to edit this draft."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Draft belongs to a tournament
        if obj.tournament:
            return can_edit_tournament(request.user, obj.tournament)
        return False


class CanEditDraftRound(permissions.BasePermission):
    """Permission check for draft round editing via tournament access."""

    message = "You do not have permission to edit this draft round."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # DraftRound belongs to Draft which belongs to Tournament
        if obj.draft and obj.draft.tournament:
            return can_edit_tournament(request.user, obj.draft.tournament)
        return False


class CanManageGame(permissions.BasePermission):
    """Permission check for game management (declare winner, link steam match)."""

    message = "You do not have permission to manage this game."

    def has_permission(self, request, view):
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return can_manage_game(request.user, obj)


class IsTournamentStaff(permissions.BasePermission):
    """Permission check for tournament staff access.

    Checks hierarchy: site admin/staff → org admin/staff → league admin/staff.
    Supports URL kwargs: tournament_id, game_id, game_pk, draft_pk.
    """

    message = "You do not have permission to modify this tournament."

    def has_permission(self, request, view):
        """Check tournament staff access."""
        if not request.user or not request.user.is_authenticated:
            return False

        # Import here to avoid circular imports
        from app.models import Game, HeroDraft, Tournament

        tournament = None

        # Try tournament_id first
        tournament_id = view.kwargs.get("tournament_id")
        if tournament_id:
            try:
                tournament = Tournament.objects.select_related("league").get(
                    pk=tournament_id
                )
            except Tournament.DoesNotExist:
                return False

        # Try game_id or game_pk
        if not tournament:
            game_id = view.kwargs.get("game_id") or view.kwargs.get("game_pk")
            if game_id:
                try:
                    game = Game.objects.select_related("tournament__league").get(
                        pk=game_id
                    )
                    tournament = game.tournament
                except Game.DoesNotExist:
                    return False

        # Try draft_pk (for herodraft views)
        if not tournament:
            draft_pk = view.kwargs.get("draft_pk")
            if draft_pk:
                try:
                    draft = HeroDraft.objects.select_related(
                        "game__tournament__league"
                    ).get(pk=draft_pk)
                    if draft.game:
                        tournament = draft.game.tournament
                except HeroDraft.DoesNotExist:
                    return False

        if not tournament:
            return False

        return can_edit_tournament(request.user, tournament)
