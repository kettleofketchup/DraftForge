"""Admin Team API views for league and tournament permission management."""

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.functions.tournament import serialize_tournament
from app.models import CustomUser, League, LeagueLog, Tournament
from app.permissions_tournament import (
    has_league_admin_access,
    has_league_staff_access,
)
from app.serializers import TournamentUserSerializer
from league.models import LeagueUser
from org.member_resolution import member_nick, resolve_member_user
from org.mmr import (
    LEAGUE_GAME,
    org_mmr_for,
)
from org.models import Organization, OrgUser
from org.permissions import (
    has_org_admin_access,
    has_org_staff_access,
)
from org.user_search import user_name_q
from user.querysets import with_user_profiles

# =============================================================================
# User Search
# =============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request: Request) -> Response:
    """
    Search users by username, nickname, Discord names, or Steam ID.

    Query params:
    - q: Search query (min 3 characters)
    - org_id: Optional org ID; also matches that org's server nicknames,
      ranks its members first and annotates membership (org staff only)
    - league_id: Optional league ID for membership annotation

    Returns max 20 results.
    """
    query = request.query_params.get("q", "").strip()

    if len(query) < 3:
        return Response(
            {"error": "Search query must be at least 3 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    org: Organization | None = None
    org_id = request.query_params.get("org_id")
    if org_id:
        try:
            org = Organization.objects.get(pk=int(org_id))
        except (Organization.DoesNotExist, ValueError):
            org = None

    if org and not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have access to this organization"},
            status=status.HTTP_403_FORBIDDEN,
        )

    q_filter = user_name_q(query, org_id=org.pk if org else None)
    if query.isdigit():
        q_filter |= Q(steamid=int(query)) | Q(steam_account_id=int(query))

    users_qs = with_user_profiles(CustomUser.objects.all(), dota=True).filter(q_filter)
    if org:
        users_qs = users_qs.annotate(
            is_org_member=Exists(
                OrgUser.objects.filter(user=OuterRef("pk"), organization=org)
            )
        ).order_by("-is_org_member", "username")
    data = TournamentUserSerializer(users_qs[:20], many=True).data

    if org:
        league = None
        league_id = request.query_params.get("league_id")
        if league_id:
            try:
                league = League.objects.get(pk=int(league_id))
            except (League.DoesNotExist, ValueError):
                pass

        user_ids = [u["pk"] for u in data]

        league_member_ids = set()
        if league:
            league_member_ids = set(
                LeagueUser.objects.filter(
                    league=league, user_id__in=user_ids
                ).values_list("user_id", flat=True)
            )

        org_nicknames: dict[int, str | None] = dict(
            OrgUser.objects.filter(organization=org, user_id__in=user_ids).values_list(
                "user_id", "guild_nickname"
            )
        )
        org_member_ids = set(org_nicknames)

        other_org_map = {}
        remaining_ids = set(user_ids) - org_member_ids - league_member_ids
        if remaining_ids:
            other_memberships = (
                OrgUser.objects.filter(user_id__in=remaining_ids)
                .select_related("organization")
                .values_list("user_id", "organization__name")
            )
            for uid, org_name in other_memberships:
                if uid not in other_org_map:
                    other_org_map[uid] = org_name

        for user_data in data:
            uid = user_data["pk"]
            user_data["guildNickname"] = org_nicknames.get(uid)
            if uid in league_member_ids:
                user_data["membership"] = "league"
                user_data["membership_label"] = league.name if league else ""
            elif uid in org_member_ids:
                user_data["membership"] = "org"
                user_data["membership_label"] = org.name
            elif uid in other_org_map:
                user_data["membership"] = "other_org"
                user_data["membership_label"] = other_org_map[uid]
            else:
                user_data["membership"] = None
                user_data["membership_label"] = None

    return Response(data)


# =============================================================================
# League Admin Team Management
# =============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_admin(request: Request, league_id: int) -> Response:
    """Add an admin to a league. Requires org admin access."""
    try:
        league = League.objects.select_related("organization").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if user is admin of the linked organization
    has_access = league.organization and has_org_admin_access(
        request.user, league.organization
    )

    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission to manage this league"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user_id = request.data.get("user_id")
    if not user_id:
        return Response(
            {"error": "user_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    league.admins.add(user)
    invalidate_obj(league)

    # Log the action
    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="add_admin",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_league_admin(request: Request, league_id: int, user_id: int) -> Response:
    """Remove an admin from a league. Requires org admin access."""
    try:
        league = League.objects.select_related("organization").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if user is admin of the linked organization
    has_access = league.organization and has_org_admin_access(
        request.user, league.organization
    )

    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission to manage this league"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    league.admins.remove(user)
    invalidate_obj(league)

    # Log the action
    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="remove_admin",
        target_user=user,
    )

    return Response({"status": "removed"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_staff(request: Request, league_id: int) -> Response:
    """Add staff to a league. Requires org admin or league admin access."""
    try:
        league = League.objects.select_related("organization").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not has_league_admin_access(request.user, league):
        return Response(
            {"error": "You do not have permission to manage this league"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user_id = request.data.get("user_id")
    if not user_id:
        return Response(
            {"error": "user_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    league.staff.add(user)
    invalidate_obj(league)

    # Log the action
    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="add_staff",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_league_staff(request: Request, league_id: int, user_id: int) -> Response:
    """Remove staff from a league. Requires org admin or league admin access."""
    try:
        league = League.objects.select_related("organization").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not has_league_admin_access(request.user, league):
        return Response(
            {"error": "You do not have permission to manage this league"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    league.staff.remove(user)
    invalidate_obj(league)

    # Log the action
    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="remove_staff",
        target_user=user,
    )

    return Response({"status": "removed"})


# =============================================================================
# Member Management (League, Tournament)
# =============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_member(request: Request, league_id: int) -> Response:
    """Add a member to a league. Creates LeagueUser (and OrgUser if needed)."""
    league = get_object_or_404(
        League.objects.select_related("organization"), pk=league_id
    )

    if not has_league_admin_access(request.user, league):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    result = resolve_member_user(request.data, org=league.organization)
    if isinstance(result, Response):
        return result
    user, member = result

    try:
        with transaction.atomic():
            org_user, _ = OrgUser.objects.get_or_create(
                user=user, organization=league.organization
            )
            nick = member_nick(member)
            if org_user.guild_nickname is None and nick is not None:
                org_user.guild_nickname = nick
                org_user.save(update_fields=["guild_nickname"])
            LeagueUser.objects.create(
                user=user,
                org_user=org_user,
                league=league,
                mmr=org_mmr_for(league.organization_id, user.pk, LEAGUE_GAME),
            )
            invalidate_after_commit(user)
    except IntegrityError:
        return Response(
            {"error": "User is already a member of this league"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="add_member",
        target_user=user,
    )
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_tournament_member(request: Request, tournament_id: int) -> Response:
    """Add a member to a tournament's users M2M."""
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    # Check access via league staff (includes org staff + league-specific staff)
    has_access = False
    if tournament.league:
        has_access = has_league_staff_access(request.user, tournament.league)
    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org = tournament.league.organization if tournament.league else None
    result = resolve_member_user(request.data, org=org)
    if isinstance(result, Response):
        return result
    user, _ = result

    if tournament.users.filter(pk=user.pk).exists():
        return Response(
            {"error": "User is already in this tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tournament.users.add(user)

    invalidate_obj(tournament)
    invalidate_after_commit(tournament)

    tournament.refresh_from_db()
    return Response({"status": "added", "tournament": serialize_tournament(tournament)})
