"""Organization admin-team and member management API views."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone as tz
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser
from app.serializers import TournamentUserSerializer
from app.steam_accounts import (
    steam_account_id_conflict_payload,
    steam_account_id_holder,
)
from events.eligibility import refresh_unmet_requirements
from league.models import LeagueUser
from org.member_resolution import member_nick, resolve_member_user
from org.models import Organization, OrgLog, OrgUser
from org.permissions import (
    has_org_admin_access,
    has_org_staff_access,
    is_org_owner,
)
from org.serializers import OrgUserSerializer
from user.querysets import with_user_profiles


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_admin(request: Request, org_id: int) -> Response:
    """Add an admin to an organization. Requires owner or admin access."""
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": "Organization not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not has_org_admin_access(request.user, org):
        return Response(
            {"error": "You do not have permission to manage this organization"},
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

    # Don't add owner as admin
    if org.owner_id == user.pk:
        return Response(
            {"error": "Owner cannot be added as admin"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    org.admins.add(user)
    OrgUser.objects.get_or_create(user=user, organization=org)
    invalidate_obj(org)

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="add_admin",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_org_admin(request: Request, org_id: int, user_id: int) -> Response:
    """Remove an admin from an organization. Requires owner access."""
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": "Organization not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Only owner or superuser can remove admins
    if not (is_org_owner(request.user, org) or request.user.is_superuser):
        return Response(
            {"error": "Only owner can remove admins"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    org.admins.remove(user)
    invalidate_obj(org)

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="remove_admin",
        target_user=user,
    )

    return Response({"status": "removed"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_staff(request: Request, org_id: int) -> Response:
    """Add staff to an organization. Requires owner or admin access."""
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": "Organization not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not has_org_admin_access(request.user, org):
        return Response(
            {"error": "You do not have permission to manage this organization"},
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

    org.staff.add(user)
    OrgUser.objects.get_or_create(user=user, organization=org)
    invalidate_obj(org)

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="add_staff",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_org_staff(request: Request, org_id: int, user_id: int) -> Response:
    """Remove staff from an organization. Requires owner or admin access."""
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": "Organization not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not has_org_admin_access(request.user, org):
        return Response(
            {"error": "You do not have permission to manage this organization"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    org.staff.remove(user)
    invalidate_obj(org)

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="remove_staff",
        target_user=user,
    )

    return Response({"status": "removed"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transfer_org_ownership(request: Request, org_id: int) -> Response:
    """Transfer organization ownership. Requires owner or superuser access."""
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": "Organization not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Only owner or superuser can transfer ownership
    if not (is_org_owner(request.user, org) or request.user.is_superuser):
        return Response(
            {"error": "Only owner or site admin can transfer ownership"},
            status=status.HTTP_403_FORBIDDEN,
        )

    new_owner_id = request.data.get("user_id")
    if not new_owner_id:
        return Response(
            {"error": "user_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        new_owner = CustomUser.objects.get(pk=new_owner_id)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # New owner must be an admin (or current owner can transfer to anyone)
    if (
        not org.admins.filter(pk=new_owner.pk).exists()
        and not request.user.is_superuser
    ):
        return Response(
            {"error": "New owner must be an existing admin"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    old_owner = org.owner

    org.owner = new_owner
    org.save(update_fields=["owner"])

    # Remove new owner from admins (owner is separate role)
    org.admins.remove(new_owner)

    # Add old owner as admin (if they existed)
    if old_owner:
        org.admins.add(old_owner)

    invalidate_obj(org)

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="transfer_ownership",
        target_user=new_owner,
        details={"previous_owner_id": old_owner.pk if old_owner else None},
    )

    return Response(
        {
            "status": "transferred",
            "new_owner": TournamentUserSerializer(new_owner).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_member(request: Request, org_id: int) -> Response:
    """Add a member to an organization. Creates OrgUser record."""
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    result = resolve_member_user(request.data, org=org)
    if isinstance(result, Response):
        return result
    user, member = result

    try:
        with transaction.atomic():
            OrgUser.objects.create(
                user=user, organization=org, guild_nickname=member_nick(member)
            )
            invalidate_after_commit(user)
    except IntegrityError:
        return Response(
            {"error": "User is already a member of this organization"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="add_member",
        target_user=user,
    )
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_org_user(request: Request, org_id: int, org_user_id: int) -> Response:
    """Update an OrgUser and/or its underlying CustomUser.

    OrgUser fields (e.g. mmr) are updated directly.
    Base user fields (nickname, steam_account_id, etc.) are forwarded
    to the CustomUser model so edits from the org page work end-to-end.
    """
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org_user = get_object_or_404(
        with_user_profiles(OrgUser.objects.all(), "user", dota=True),
        pk=org_user_id,
        organization=org,
    )

    # --- OrgUser-level fields ---
    ORG_USER_FIELDS = {"mmr"}
    org_updated = []
    for field in ORG_USER_FIELDS:
        if field in request.data:
            setattr(org_user, field, request.data[field])
            org_updated.append(field)

    # An admin-set MMR should count as an active, verified value so it shows
    # up wherever org_user_mmr is read (event signups, etc.). approve_signup
    # already does this; mirror it here.
    if "mmr" in request.data:
        org_user.has_active_dota_mmr = True
        org_user.dota_mmr_last_verified = tz.now()
        for f in ("has_active_dota_mmr", "dota_mmr_last_verified"):
            if f not in org_updated:
                org_updated.append(f)

    # --- Base CustomUser fields ---
    USER_FIELDS = {"nickname", "steam_account_id"}
    user = org_user.user
    user_updated = False
    for field in USER_FIELDS:
        if field in request.data:
            new_val = request.data[field]
            # Coerce empty strings to None for nullable fields
            if new_val == "" or new_val == "null":
                new_val = None
            if field == "steam_account_id" and new_val is not None:
                holder = steam_account_id_holder(new_val, exclude_pk=user.pk)
                if holder is not None:
                    return Response(
                        steam_account_id_conflict_payload(new_val, holder),
                        status=status.HTTP_409_CONFLICT,
                    )
            if getattr(user, field) != new_val:
                setattr(user, field, new_val)
                user_updated = True

    # --- Positions (nested FK) ---
    positions_data = request.data.get("positions")
    if positions_data and isinstance(positions_data, dict):
        positions_instance = user.positions
        for key in ("carry", "mid", "offlane", "soft_support", "hard_support"):
            if key in positions_data:
                val = int(positions_data[key])
                if getattr(positions_instance, key) != val:
                    setattr(positions_instance, key, val)
                    user_updated = True
        if user_updated:
            positions_instance.save()

    if not org_updated and not user_updated:
        return Response(
            {"error": "No valid fields to update"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        if org_updated:
            org_user.save(update_fields=org_updated)
        if user_updated:
            user.save()  # Full save triggers steamid sync
        refresh_unmet_requirements(org_user)

        # Invalidate all cached views affected by this change
        league_users = LeagueUser.objects.filter(org_user=org_user).select_related(
            "league"
        )
        invalidate_after_commit(
            org_user,
            org,
            *user.tournaments.all(),
            *league_users,
            *(lu.league for lu in league_users),
        )

    return Response(OrgUserSerializer(org_user).data)
