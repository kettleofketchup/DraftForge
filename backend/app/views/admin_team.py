"""Admin Team API views for organization and league permission management."""

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import CustomUser, League, LeagueLog, Organization, OrgLog
from app.permissions_org import (
    has_league_admin_access,
    has_org_admin_access,
    is_org_owner,
)
from app.serializers import TournamentUserSerializer

# =============================================================================
# User Search
# =============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request):
    """
    Search users by Discord username or nickname.

    Query params:
    - q: Search query (min 3 characters)

    Returns max 20 results.
    """
    query = request.query_params.get("q", "").strip()

    if len(query) < 3:
        return Response(
            {"error": "Search query must be at least 3 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    users = CustomUser.objects.filter(
        Q(discordUsername__icontains=query)
        | Q(discordNickname__icontains=query)
        | Q(guildNickname__icontains=query)
        | Q(username__icontains=query)
    )[:20]

    return Response(TournamentUserSerializer(users, many=True).data)


# =============================================================================
# Organization Admin Team Management
# =============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_admin(request, org_id):
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

    # Log the action
    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="add_admin",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_org_admin(request, org_id, user_id):
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

    # Log the action
    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="remove_admin",
        target_user=user,
    )

    return Response({"status": "removed"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_staff(request, org_id):
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

    # Log the action
    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="add_staff",
        target_user=user,
    )

    return Response({"status": "added", "user": TournamentUserSerializer(user).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_org_staff(request, org_id, user_id):
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

    # Log the action
    OrgLog.objects.create(
        organization=org,
        actor=request.user,
        action="remove_staff",
        target_user=user,
    )

    return Response({"status": "removed"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transfer_org_ownership(request, org_id):
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

    # Transfer ownership
    org.owner = new_owner
    org.save(update_fields=["owner"])

    # Remove new owner from admins (owner is separate role)
    org.admins.remove(new_owner)

    # Add old owner as admin (if they existed)
    if old_owner:
        org.admins.add(old_owner)

    # Log the action
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


# =============================================================================
# League Admin Team Management
# =============================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_admin(request, league_id):
    """Add an admin to a league. Requires org admin access."""
    try:
        league = League.objects.prefetch_related("organizations").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if user is admin of any linked organization
    has_access = False
    for org in league.organizations.all():
        if has_org_admin_access(request.user, org):
            has_access = True
            break

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
def remove_league_admin(request, league_id, user_id):
    """Remove an admin from a league. Requires org admin access."""
    try:
        league = League.objects.prefetch_related("organizations").get(pk=league_id)
    except League.DoesNotExist:
        return Response(
            {"error": "League not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if user is admin of any linked organization
    has_access = False
    for org in league.organizations.all():
        if has_org_admin_access(request.user, org):
            has_access = True
            break

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
def add_league_staff(request, league_id):
    """Add staff to a league. Requires org admin or league admin access."""
    try:
        league = League.objects.prefetch_related("organizations").get(pk=league_id)
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
def remove_league_staff(request, league_id, user_id):
    """Remove staff from a league. Requires org admin or league admin access."""
    try:
        league = League.objects.prefetch_related("organizations").get(pk=league_id)
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

    # Log the action
    LeagueLog.objects.create(
        league=league,
        actor=request.user,
        action="remove_staff",
        target_user=user,
    )

    return Response({"status": "removed"})
