"""Admin Team API views for organization and league permission management."""

from cacheops import invalidate_obj
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import (
    CustomUser,
    League,
    LeagueLog,
    Organization,
    OrgLog,
    PositionsModel,
    Tournament,
)
from app.permissions_org import (
    has_league_admin_access,
    has_org_admin_access,
    has_org_staff_access,
    is_org_owner,
)
from app.serializers import TournamentUserSerializer
from league.models import LeagueUser
from org.models import OrgUser

# =============================================================================
# User Search
# =============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request):
    """
    Search users by username, nickname, Discord names, or Steam ID.

    Query params:
    - q: Search query (min 3 characters)
    - org_id: Optional org ID for membership annotation
    - league_id: Optional league ID for membership annotation

    Returns max 20 results, each annotated with membership context
    when org_id is provided.
    """
    query = request.query_params.get("q", "").strip()

    if len(query) < 3:
        return Response(
            {"error": "Search query must be at least 3 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build search filter
    q_filter = (
        Q(discordUsername__icontains=query)
        | Q(discordNickname__icontains=query)
        | Q(guildNickname__icontains=query)
        | Q(username__icontains=query)
        | Q(nickname__icontains=query)
    )

    # Add Steam ID search if query is numeric
    if query.isdigit():
        q_filter |= Q(steamid=int(query)) | Q(steam_account_id=int(query))

    users = CustomUser.objects.filter(q_filter)[:20]
    data = TournamentUserSerializer(users, many=True).data

    # Annotate with membership context if org_id provided
    org_id = request.query_params.get("org_id")
    league_id = request.query_params.get("league_id")

    if org_id:
        try:
            org = Organization.objects.get(pk=int(org_id))
        except (Organization.DoesNotExist, ValueError):
            org = None

        # Require org staff access to see membership annotations
        if org and not has_org_staff_access(request.user, org):
            return Response(
                {"error": "You do not have access to this organization"},
                status=status.HTTP_403_FORBIDDEN,
            )

        league = None
        if league_id:
            try:
                league = League.objects.get(pk=int(league_id))
            except (League.DoesNotExist, ValueError):
                pass

        if org:
            user_ids = [u["pk"] for u in data]

            # Get league member IDs
            league_member_ids = set()
            if league:
                league_member_ids = set(
                    LeagueUser.objects.filter(
                        league=league, user_id__in=user_ids
                    ).values_list("user_id", flat=True)
                )

            # Get org member IDs
            org_member_ids = set(
                OrgUser.objects.filter(
                    organization=org, user_id__in=user_ids
                ).values_list("user_id", flat=True)
            )

            # Get other org memberships for remaining users
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
    invalidate_obj(org)

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
    invalidate_obj(org)

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
    invalidate_obj(org)

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
    invalidate_obj(org)

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

    invalidate_obj(org)

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
def remove_league_admin(request, league_id, user_id):
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
def add_league_staff(request, league_id):
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
def remove_league_staff(request, league_id, user_id):
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
# Member Management (Org, League, Tournament)
# =============================================================================


def _resolve_user(data, org=None):
    """
    Resolve a user from user_id or discord_id. Returns User or error Response.

    When discord_id is provided, the backend looks up the Discord member data
    from its own Redis cache (trust boundary -- never trust client-supplied data).
    """
    user_id = data.get("user_id")
    discord_id = data.get("discord_id")

    if user_id:
        try:
            return CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
    elif discord_id:
        # Check if user already exists with this Discord ID
        existing = CustomUser.objects.filter(discordId=discord_id).first()
        if existing:
            return existing

        # Look up Discord data from our own cache (not client-supplied)
        if not org or not org.discord_server_id:
            return Response(
                {"error": "Cannot resolve Discord user without org Discord server"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"discord_members_search_{org.discord_server_id}"
        members = cache.get(cache_key)
        if not members:
            return Response(
                {
                    "error": "Discord member cache is empty. "
                    "Please refresh Discord members first."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Find the member in the cached list
        discord_member = None
        for m in members:
            if m.get("user", {}).get("id") == discord_id:
                discord_member = m
                break

        if not discord_member:
            return Response(
                {"error": "Discord member not found in cache"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Auto-create from cached Discord data
        positions = PositionsModel.objects.create()
        user = CustomUser(positions=positions)
        user.createFromDiscordData(discord_member)
        user.save()
        return user
    else:
        return Response(
            {"error": "user_id or discord_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_org_member(request, org_id):
    """Add a member to an organization. Creates OrgUser record."""
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = _resolve_user(request.data, org=org)
    if isinstance(user, Response):
        return user  # Error response

    try:
        OrgUser.objects.create(user=user, organization=org)
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
def update_org_user(request, org_id, org_user_id):
    """Update an OrgUser's fields (e.g. MMR)."""
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org_user = get_object_or_404(
        OrgUser.objects.select_related("user"), pk=org_user_id, organization=org
    )

    ALLOWED_FIELDS = {"mmr"}
    updated = []
    for field in ALLOWED_FIELDS:
        if field in request.data:
            setattr(org_user, field, request.data[field])
            updated.append(field)

    if not updated:
        return Response(
            {"error": "No valid fields to update"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    org_user.save(update_fields=updated)
    invalidate_obj(org_user)
    invalidate_obj(org)

    # Invalidate cached tournament responses that include this user's MMR
    for tournament in org_user.user.tournament_set.all():
        invalidate_obj(tournament)

    from org.serializers import OrgUserSerializer

    return Response(OrgUserSerializer(org_user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_league_member(request, league_id):
    """Add a member to a league. Creates LeagueUser (and OrgUser if needed)."""
    league = get_object_or_404(
        League.objects.select_related("organization"), pk=league_id
    )

    if not has_league_admin_access(request.user, league):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = _resolve_user(request.data, org=league.organization)
    if isinstance(user, Response):
        return user

    try:
        with transaction.atomic():
            org_user, _ = OrgUser.objects.get_or_create(
                user=user, organization=league.organization
            )
            LeagueUser.objects.create(user=user, org_user=org_user, league=league)
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
def add_tournament_member(request, tournament_id):
    """Add a member to a tournament's users M2M."""
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    # Check access via league's org
    has_access = False
    if tournament.league and tournament.league.organization:
        has_access = has_org_staff_access(request.user, tournament.league.organization)
    if not has_access and not request.user.is_superuser:
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org = tournament.league.organization if tournament.league else None
    user = _resolve_user(request.data, org=org)
    if isinstance(user, Response):
        return user

    if tournament.users.filter(pk=user.pk).exists():
        return Response(
            {"error": "User is already in this tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tournament.users.add(user)
    return Response({"status": "added", "user": TournamentUserSerializer(user).data})
