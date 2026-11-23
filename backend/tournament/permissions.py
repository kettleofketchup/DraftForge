"""Tournament and game permission helpers."""

from typing import Any

from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions, serializers
from rest_framework.request import Request

from app.models import CustomUser, Game, Tournament
from draft.models import HeroDraft
from league.models import League
from league.permissions import has_league_admin_access, has_league_staff_access


def can_edit_tournament(
    user: CustomUser | AnonymousUser, tournament: Tournament
) -> bool:
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

    if user.is_superuser or user.is_staff:
        return True

    # League staff access includes org admin/staff of the league's org.
    if tournament.league:
        return has_league_staff_access(user, tournament.league)

    return False


def can_create_team(
    user: CustomUser | AnonymousUser, tournament: Tournament | None
) -> bool:
    """Tournament staff create teams in their tournament; only site staff create loose teams."""
    if tournament is None:
        return user.is_authenticated and (user.is_superuser or user.is_staff)
    return can_edit_tournament(user, tournament)


def _league_change_error(message: str) -> serializers.ValidationError:
    return serializers.ValidationError({"league_id_write": message})


def check_tournament_league_change(
    user: CustomUser | AnonymousUser,
    tournament: Tournament | None,
    target: League | None,
) -> None:
    """Authorize setting a tournament's league; ``tournament=None`` means create."""
    if tournament is not None and target == tournament.league:
        return
    is_site_staff = user.is_staff or user.is_superuser
    if target is None:
        if tournament is None:
            raise _league_change_error(
                "A league is required when creating a tournament."
            )
        if not is_site_staff:
            raise _league_change_error(
                "Only site staff can remove a tournament's league."
            )
        return
    if tournament is not None:
        event = tournament.source_event.nocache().first()
        if event is not None and target.organization_id != event.organization_id:
            raise _league_change_error(
                "League must belong to the event's organization."
            )
        if tournament.league is not None and not has_league_admin_access(
            user, tournament.league
        ):
            raise _league_change_error(
                "You must be an admin of the tournament's current league to move it."
            )
    if not has_league_admin_access(user, target):
        raise _league_change_error(
            "You must be an admin of this league to create a tournament in it."
            if tournament is None
            else "You must be an admin of the league you are moving this tournament to."
        )


def can_manage_game(user: CustomUser | AnonymousUser, game: Game) -> bool:
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

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return can_edit_tournament(request.user, obj)


class CanEditTeam(permissions.BasePermission):
    """Permission check for team editing via tournament access."""

    message = "You do not have permission to edit this team."

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        # Team belongs to a tournament
        if obj.tournament:
            return can_edit_tournament(request.user, obj.tournament)
        return False


class CanManageGame(permissions.BasePermission):
    """Permission check for game management (declare winner, link steam match)."""

    message = "You do not have permission to manage this game."

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return can_manage_game(request.user, obj)


class IsTournamentStaff(permissions.BasePermission):
    """Permission check for tournament staff access.

    Checks hierarchy: site admin/staff → org admin/staff → league admin/staff.
    Supports URL kwargs: tournament_id, game_id, game_pk, draft_pk.
    """

    message = "You do not have permission to modify this tournament."

    def has_permission(self, request: Request, view: object) -> bool:
        """Check tournament staff access."""
        if not request.user or not request.user.is_authenticated:
            return False

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
