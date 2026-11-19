"""Steam ID helpers shared by the eligibility checks and the signup flows."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile
from telemetry.logging import get_logger

log = get_logger(__name__)

# Steam account IDs are unsigned 32-bit; 0 is never assigned.
STEAM_ACCOUNT_ID_RANGE = range(1, 2**32)
# Range of the CustomUser.steam_account_id IntegerField.
STORED_STEAM_ACCOUNT_ID_MAX = 2**31 - 1
FRIEND_ID_MAX_LENGTH = 20

_PROFILE_ATTRS = ("dota_profile", "deadlock_profile")


def steam_friend_id_from_profiles(org_user: OrgUser | None) -> str:
    """First numeric friend ID across the game profiles; ``""`` if none.

    One Steam account backs both games, so either profile identifies it.
    """
    if org_user is None:
        return ""
    for attr in _PROFILE_ATTRS:
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        value = (value or "").strip()
        if value.isascii() and value.isdigit():
            return value
    return ""


def _raw_friend_id_from_profiles(org_user: OrgUser) -> str:
    for attr in _PROFILE_ATTRS:
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        if (value or "").strip():
            return value.strip()
    return ""


def sync_steam_account_from_profiles(
    user: CustomUser, org: Organization | None, *, event_id: int | None = None
) -> bool:
    """Copy the profile friend ID onto an empty ``user.steam_account_id``.

    Never raises for bad data: a conflict, out-of-range or non-numeric ID is
    logged, ``user`` is reloaded, and False is returned. True when it wrote.
    """
    if org is None or user.steam_account_id:
        return False
    org_user = OrgUser.objects.filter(user=user, organization=org).first()
    if org_user is None:
        return False
    fid = steam_friend_id_from_profiles(org_user)
    if not fid:
        if _raw_friend_id_from_profiles(org_user):
            _log_writethrough_skipped(user, event_id, reason="non_numeric")
        return False
    account_id = int(fid)
    if account_id not in STEAM_ACCOUNT_ID_RANGE or (
        account_id > STORED_STEAM_ACCOUNT_ID_MAX
    ):
        _log_writethrough_skipped(user, event_id, reason="out_of_range")
        return False
    try:
        with transaction.atomic():
            user.steam_account_id = account_id
            user.save(update_fields=["steam_account_id", "steamid"])
    except IntegrityError:
        user.refresh_from_db(fields=["steam_account_id", "steamid"])
        conflicting_user_id = (
            CustomUser.objects.filter(steam_account_id=account_id)
            .exclude(pk=user.pk)
            .values_list("pk", flat=True)
            .first()
        )
        _log_writethrough_skipped(
            user,
            event_id,
            reason="conflict",
            conflicting_user_id=conflicting_user_id,
        )
        return False
    invalidate_after_commit(user)
    return True


def _log_writethrough_skipped(
    user: CustomUser,
    event_id: int | None,
    *,
    reason: str,
    conflicting_user_id: int | None = None,
) -> None:
    log.warning(
        "signup_steam_writethrough_skipped",
        system="events",
        subsystem="services",
        tags=["events", "signup"],
        tags_csv="events,signup",
        reason=reason,
        user_id=user.pk,
        event_id=event_id,
        conflicting_user_id=conflicting_user_id,
    )


def validate_friend_id(fid: str, org_user: OrgUser) -> str:
    """Return ``fid`` in canonical form (stripped, no leading zeros), or
    raise if it is malformed or owned by another user (any of their game
    profiles in any org, or their Steam account).

    ``""`` is returned as-is so callers can clear the field.
    """
    fid = fid.strip()
    if not fid:
        return fid
    if not (fid.isascii() and fid.isdigit()) or len(fid) > FRIEND_ID_MAX_LENGTH:
        raise ValidationError(
            f"Friend ID must be digits only (max {FRIEND_ID_MAX_LENGTH}).",
            code="invalid_friend_id",
        )
    fid = str(int(fid))
    # Global scope: Friend ID is unique site-wide, not per-org.
    collision = any(
        model.objects.filter(unverified_friend_id=fid)
        .exclude(org_user__user_id=org_user.user_id)
        .exists()
        for model in (PlayerDotaProfile, PlayerDeadlockProfile)
    )
    account_id = int(fid)
    if not collision and account_id <= STORED_STEAM_ACCOUNT_ID_MAX:
        collision = (
            CustomUser.objects.filter(steam_account_id=account_id)
            .exclude(pk=org_user.user_id)
            .exists()
        )
    if collision:
        raise ValidationError(
            f"Friend ID {fid} is already registered to another account. "
            f"Contact an admin or login to {settings.SITE_URL} to claim it.",
            code="duplicate_friend_id",
        )
    return fid
