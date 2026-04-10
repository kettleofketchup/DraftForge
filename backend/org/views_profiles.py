"""API views for player profiles scoped to organizations."""

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from app.permissions_org import has_org_staff_access
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile

DOTA_PROFILE_FIELDS = {
    "rank_status",
    "rank_medal",
    "rank_date",
    "battle_cup_tier",
    "mmr",
    "rank_screenshot",
    "battlecup_screenshot",
    "pos_1",
    "pos_2",
    "pos_3",
    "pos_4",
    "pos_5",
    "unverified_friend_id",
}


def _serialize_dota_profile(profile):
    return {
        "id": profile.pk,
        "org_user_id": profile.org_user_id,
        "rank_status": profile.rank_status,
        "rank_medal": profile.rank_medal,
        "rank_date": profile.rank_date.isoformat() if profile.rank_date else None,
        "battle_cup_tier": profile.battle_cup_tier,
        "mmr": profile.mmr,
        "rank_screenshot": profile.rank_screenshot or None,
        "battlecup_screenshot": profile.battlecup_screenshot or None,
        "unverified_friend_id": profile.unverified_friend_id,
        "pos_1": profile.pos_1,
        "pos_2": profile.pos_2,
        "pos_3": profile.pos_3,
        "pos_4": profile.pos_4,
        "pos_5": profile.pos_5,
    }


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_my_dota_profile(request, org_id):
    """Get the current user's Dota 2 profile for an organization.
    GET /api/organizations/<org_id>/my-dota-profile/
    """
    try:
        org_user = OrgUser.objects.get(user=request.user, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "Not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    return Response(_serialize_dota_profile(profile))


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_my_dota_profile(request, org_id):
    """Update the current user's Dota 2 profile for an organization.
    PATCH /api/organizations/<org_id>/my-dota-profile/
    """
    try:
        org_user = OrgUser.objects.get(user=request.user, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "Not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    for field in DOTA_PROFILE_FIELDS:
        if field in request.data:
            setattr(profile, field, request.data[field])
    profile.save()

    from cacheops import invalidate_obj

    invalidate_obj(profile)
    invalidate_obj(org_user)

    return Response(_serialize_dota_profile(profile))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_user_dota_profile(request, org_id, user_pk):
    """Get any user's Dota 2 profile for an org (org staff only).
    GET /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    from app.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = OrgUser.objects.get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "User is not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    return Response(_serialize_dota_profile(profile))


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_user_dota_profile(request, org_id, user_pk):
    """Update any user's Dota 2 profile (org staff only).
    PATCH /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    from app.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = OrgUser.objects.get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "User is not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    for field in DOTA_PROFILE_FIELDS:
        if field in request.data:
            setattr(profile, field, request.data[field])
    profile.save()

    from cacheops import invalidate_obj

    invalidate_obj(profile)
    invalidate_obj(org_user)

    return Response(_serialize_dota_profile(profile))


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def delete_user_dota_profile(request, org_id, user_pk):
    """Delete a user's Dota 2 profile (org staff only).
    DELETE /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    from app.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = OrgUser.objects.get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    deleted, _ = PlayerDotaProfile.objects.filter(org_user=org_user).delete()
    if deleted:
        from cacheops import invalidate_obj

        invalidate_obj(org_user)
    return Response(status=status.HTTP_204_NO_CONTENT)
