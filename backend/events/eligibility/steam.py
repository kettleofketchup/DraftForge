"""The player's Steam Friend ID, stored once on ``CustomUser.steam_account_id``."""

from __future__ import annotations

from typing import Final

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from app.permissions_steam import VerifyGrant, can_verify_steam_account
from app.steam_accounts import (
    log_steam_verification_change,
    mark_steam_account_verified,
    steam_account_id_holder,
)
from events.models import Event
from steam.services.account_lookup import (
    SteamLookupRateLimited,
    ensure_steam_account_exists,
    steam_account_exists,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

# Steam account IDs are unsigned 32-bit; 0 is never assigned.
STEAM_ACCOUNT_ID_RANGE: Final[range] = range(1, 2**32)
FRIEND_ID_MAX_LENGTH: Final[int] = 20


def _duplicate_error(account_id: int) -> ValidationError:
    return ValidationError(
        f"Friend ID {account_id} is already registered to another account. "
        f"Contact an admin or login to {settings.SITE_URL} to claim it. "
        "If this is your account, contact an organizer.",
        code="duplicate_friend_id",
    )


def _not_found_error(account_id: int) -> ValidationError:
    return ValidationError(
        f"No Steam account has Friend ID {account_id}. Check the number on your "
        "Dota 2 profile or Steam friends page.",
        code="steam_account_not_found",
    )


def _normalise_friend_id(fid: str | None) -> int | None:
    """The integer Friend ID in ``fid``, or None when blank."""
    fid = (fid or "").strip()
    if not fid:
        return None
    if not (fid.isascii() and fid.isdigit()) or len(fid) > FRIEND_ID_MAX_LENGTH:
        raise ValidationError(
            f"Friend ID must be digits only (max {FRIEND_ID_MAX_LENGTH}).",
            code="invalid_friend_id",
        )
    account_id = int(fid)
    if account_id not in STEAM_ACCOUNT_ID_RANGE:
        raise ValidationError(
            f"Friend ID must be between 1 and {STEAM_ACCOUNT_ID_RANGE.stop - 1}.",
            code="invalid_friend_id",
        )
    return account_id


def _local_checks(
    fid: str | None, user: CustomUser, *, allow_change: bool
) -> int | None:
    account_id = _normalise_friend_id(fid)
    if account_id is None or user.steam_account_id == account_id:
        return None
    if user.steam_account_id is not None and not allow_change:
        raise ValidationError(
            f"Your Friend ID is already set to {user.steam_account_id}; "
            "contact an admin to change it.",
            code="friend_id_already_set",
        )
    if steam_account_id_holder(account_id, exclude_pk=user.pk) is not None:
        raise _duplicate_error(account_id)
    return account_id


def precheck_friend_id(
    fid: str | None,
    user: CustomUser,
    *,
    allow_change: bool = False,
    budget_user: CustomUser | None = None,
) -> int | None:
    """Local checks, then the Steam lookup. Call outside any atomic block.

    Returns the Friend ID to store, or None when nothing changes.
    """
    account_id = _local_checks(fid, user, allow_change=allow_change)
    if account_id is None:
        return None
    try:
        exists = ensure_steam_account_exists(
            account_id, budget_user=budget_user or user
        )
    except SteamLookupRateLimited as exc:
        raise ValidationError(
            "Too many Friend ID checks. Try again in an hour.",
            code="steam_lookup_rate_limited",
        ) from exc
    if exists is False:
        raise _not_found_error(account_id)
    return account_id


def admin_precheck_steam_account_id(
    user: CustomUser, new_id: int | None, *, actor: CustomUser | None
) -> None:
    """Steam lookup for an untrusted staff write, charged to the actor.

    Call outside any atomic block. Trusted writes and unchanged IDs skip it.
    """
    if new_id is None or new_id == user.steam_account_id:
        return
    if can_verify_steam_account(actor, user) is not None:
        return
    precheck_friend_id(str(new_id), user, allow_change=True, budget_user=actor or user)


def apply_admin_steam_account_id(
    user: CustomUser, new_id: int | None, *, actor: CustomUser | None
) -> VerifyGrant | None:
    """Assign a staff-entered Friend ID; a trusted actor verifies a changed one.

    The caller saves, then logs the returned grant with
    ``log_steam_verification_change``.
    """
    changed = user.steam_account_id != new_id
    user.steam_account_id = new_id
    if not changed or new_id not in STEAM_ACCOUNT_ID_RANGE or actor is None:
        return None
    grant = can_verify_steam_account(actor, user)
    if grant is not None:
        mark_steam_account_verified(user, actor, org_id=grant.org_id, save=False)
    return grant


def validate_friend_id(
    fid: str | None,
    user: CustomUser,
    *,
    allow_change: bool = False,
    check_exists: bool = True,
) -> int | None:
    """The Friend ID to store on ``user``, or None when nothing changes.

    Blank input and the user's current ID are no-ops. Raises ValidationError
    for a malformed ID, a different ID than the one already set (unless
    ``allow_change``), an ID another user holds, or, with ``check_exists``,
    an ID the cached Steam lookup says has no account. Safe inside atomic.
    """
    account_id = _local_checks(fid, user, allow_change=allow_change)
    if account_id is None:
        return None
    if check_exists and steam_account_exists(account_id, cache_only=True) is False:
        raise _not_found_error(account_id)
    return account_id


def claim_friend_id(
    user: CustomUser,
    fid: str | None,
    *,
    event: Event | None = None,
    verified_by: CustomUser | None = None,
) -> int | None:
    """Validate ``fid`` and store it on an empty ``user.steam_account_id``.

    A ``verified_by`` actor allowed to vouch for ``user`` verifies the ID in
    the same save. Returns the stored ID, or None when nothing was written.
    """
    account_id = validate_friend_id(fid, user, check_exists=False)
    if account_id is None:
        return None
    grant = can_verify_steam_account(verified_by, user)
    if grant is None and steam_account_exists(account_id, cache_only=True) is False:
        raise _not_found_error(account_id)
    update_fields = ["steam_account_id", "steamid"]
    try:
        with transaction.atomic():
            user.steam_account_id = account_id
            if steam_account_exists(account_id, cache_only=True) is True:
                user.steam_account_exists_checked_at = timezone.now()
                update_fields.append("steam_account_exists_checked_at")
            if grant is not None:
                mark_steam_account_verified(
                    user, verified_by, org_id=grant.org_id, save=False
                )
            user.save(update_fields=update_fields)
    except IntegrityError as exc:
        user.refresh_from_db(
            fields=[
                "steam_account_id",
                "steamid",
                *CustomUser.STEAM_VERIFICATION_FIELDS,
            ]
        )
        raise _duplicate_error(account_id) from exc
    if grant is not None:
        log_steam_verification_change(user, verified_by, grant.org_id, True)
    invalidate_after_commit(user)
    if event is not None and event.tournament_id is not None:
        invalidate_after_commit(event.tournament)
    log.info(
        "steam_friend_id_set",
        system="events",
        subsystem="services",
        tags=["events", "signup"],
        tags_csv="events,signup",
        user_id=user.pk,
        event_id=event.pk if event is not None else None,
        verified=user.steam_account_verified,
    )
    return account_id
