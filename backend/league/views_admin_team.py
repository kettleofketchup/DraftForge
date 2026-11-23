"""League admin, staff and member management API views."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser
from app.serializers import TournamentUserSerializer
from league.mmr_sync import league_mmr_seeds
from league.models import League, LeagueLog, LeagueUser
from league.permissions import has_league_admin_access
from org.member_resolution import member_nick, resolve_member_user
from org.mmr import LEAGUE_GAME, org_mmr_for
from org.models import OrgUser
from org.permissions import has_org_admin_access


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

    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="remove_staff",
        target_user=user,
    )

    return Response({"status": "removed"})


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
                mmr=league_mmr_seeds(
                    {user.pk: org_mmr_for(league.organization_id, user.pk, LEAGUE_GAME)}
                )[user.pk],
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
