"""API views for player profiles scoped to organizations."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_obj
from app.models import CustomUser
from app.permissions_steam import can_verify_steam_account
from events.eligibility import (
    claim_friend_id,
    precheck_friend_id,
    refresh_unmet_requirements,
    validate_friend_id,
)
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDotaProfile
from org.permissions import has_org_staff_access
from user.querysets import with_user_profiles

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
}
FRIEND_ID_FIELD = "steam_account_id"


def _friend_id_error(exc: ValidationError) -> Response:
    http_status = (
        status.HTTP_429_TOO_MANY_REQUESTS
        if exc.code == "steam_lookup_rate_limited"
        else status.HTTP_400_BAD_REQUEST
    )
    return Response(
        {FRIEND_ID_FIELD: exc.messages[0], "code": exc.code}, status=http_status
    )


def _serialize_dota_profile(
    profile: PlayerDotaProfile, org_user: OrgUser
) -> dict[str, Any]:
    user = org_user.user
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
        FRIEND_ID_FIELD: user.steam_account_id,
        "steam_account_verified": user.steam_account_verified,
        "steam_account_verified_at": (
            user.steam_account_verified_at.isoformat()
            if user.steam_account_verified_at
            else None
        ),
        "steam_account_verified_org_name": user.steam_account_verified_org_name,
        "steam_account_exists_checked": user.steam_account_exists_checked,
        "pos_1": profile.pos_1,
        "pos_2": profile.pos_2,
        "pos_3": profile.pos_3,
        "pos_4": profile.pos_4,
        "pos_5": profile.pos_5,
    }


def _org_users() -> QuerySet[OrgUser]:
    return with_user_profiles(OrgUser.objects.all(), "user", steam_verified_org=True)


def _invalid_rank_status(data: dict[str, Any]) -> Response | None:
    if "rank_status" in data and (
        data["rank_status"] not in PlayerDotaProfile.RANK_STATUSES
    ):
        return Response(
            {
                "rank_status": (
                    f"Must be one of {', '.join(PlayerDotaProfile.RANK_STATUSES)}."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _friend_id(data: dict[str, Any]) -> str:
    return str(data.get(FRIEND_ID_FIELD) or "")


def _apply_dota_profile_patch(
    org_user: OrgUser, data: dict[str, Any], *, actor: CustomUser
) -> PlayerDotaProfile:
    """Raises ValidationError for a bad friend ID before writing anything.

    The Steam existence pre-check is the caller's job (outside atomic).
    """
    fields = {f: data[f] for f in DOTA_PROFILE_FIELDS if f in data}
    user = org_user.user
    friend_id = _friend_id(data)
    validate_friend_id(friend_id, user, check_exists=False)
    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    previous_status = profile.rank_status
    for field, value in fields.items():
        setattr(profile, field, value)
    profile.sync_rank_declaration(previous_status)
    claim_friend_id(user, friend_id, verified_by=actor)
    profile.save()
    invalidate_obj(profile)
    invalidate_obj(org_user)
    refresh_unmet_requirements(org_user)
    return profile


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_my_dota_profile(request: Request, org_id: int) -> Response:
    """Get the current user's Dota 2 profile for an organization.
    GET /api/organizations/<org_id>/my-dota-profile/
    """
    try:
        org_user = _org_users().get(user=request.user, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "Not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    return Response(_serialize_dota_profile(profile, org_user))


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_my_dota_profile(request: Request, org_id: int) -> Response:
    """Update the current user's Dota 2 profile for an organization.
    PATCH /api/organizations/<org_id>/my-dota-profile/
    """
    try:
        org_user = _org_users().get(user=request.user, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "Not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if (error := _invalid_rank_status(request.data)) is not None:
        return error
    try:
        precheck_friend_id(_friend_id(request.data), request.user)
        profile = _apply_dota_profile_patch(org_user, request.data, actor=request.user)
    except ValidationError as e:
        return _friend_id_error(e)
    return Response(_serialize_dota_profile(profile, org_user))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_user_dota_profile(request: Request, org_id: int, user_pk: int) -> Response:
    """Get any user's Dota 2 profile for an org (org staff only).
    GET /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = _org_users().get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "User is not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    return Response(_serialize_dota_profile(profile, org_user))


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_user_dota_profile(request: Request, org_id: int, user_pk: int) -> Response:
    """Update any user's Dota 2 profile (org staff only).
    PATCH /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = _org_users().get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(
            {"error": "User is not a member of this organization"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if (error := _invalid_rank_status(request.data)) is not None:
        return error
    try:
        if can_verify_steam_account(request.user, org_user.user) is None:
            precheck_friend_id(
                _friend_id(request.data), org_user.user, budget_user=request.user
            )
        profile = _apply_dota_profile_patch(org_user, request.data, actor=request.user)
    except ValidationError as e:
        return _friend_id_error(e)
    return Response(_serialize_dota_profile(profile, org_user))


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def delete_user_dota_profile(request: Request, org_id: int, user_pk: int) -> Response:
    """Delete a user's Dota 2 profile (org staff only).
    DELETE /api/organizations/<org_id>/users/<user_pk>/dota-profile/
    """
    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, org):
        return Response(status=status.HTTP_403_FORBIDDEN)

    try:
        org_user = _org_users().get(user_id=user_pk, organization_id=org_id)
    except OrgUser.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    deleted, _ = PlayerDotaProfile.objects.filter(org_user=org_user).delete()
    if deleted:
        invalidate_obj(org_user)
        refresh_unmet_requirements(org_user)
    return Response(status=status.HTTP_204_NO_CONTENT)
