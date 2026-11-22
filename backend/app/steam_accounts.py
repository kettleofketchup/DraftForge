"""Shared steam_account_id collision and verification helpers.

CustomUser.steam_account_id is unique=True, so every write path needs the
same "who already holds this?" question answered the same way. Used by the
org-scoped update view and the lookup endpoint the edit form calls on blur;
the global endpoint is covered by a UniqueValidator on UserSerializer
instead.

Verification mutators compare-and-set on the ID and only touch the
verification columns, so they never race an ID change into a stale vouch.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.display_names import user_display_name
from app.models import CustomUser
from app.permissions_steam import can_verify_steam_account
from telemetry.logging import get_logger

log = get_logger(__name__)

_VERIFICATION_ATTNAMES: tuple[str, ...] = (
    "steam_account_verified_at",
    "steam_account_verified_by_id",
    "steam_account_verified_org_id",
)


def steam_account_id_holder(
    steam_account_id: int | None, *, exclude_pk: int | None = None
) -> CustomUser | None:
    """Return the user already holding this Friend ID, or None if it is free."""
    if steam_account_id is None:
        return None
    qs = CustomUser.objects.filter(steam_account_id=steam_account_id)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def steam_account_id_identity(user: CustomUser) -> dict[str, Any]:
    """Identify a Friend ID holder for display.

    Names only — the same fields GET /api/users/ already exposes to any
    authenticated user.
    """
    return {
        "pk": user.pk,
        "nickname": user.nickname or "",
        "discordNickname": user.discordNickname,
        "username": user.username,
    }


def steam_account_id_conflict_payload(
    steam_account_id: int, holder: CustomUser
) -> dict[str, Any]:
    """Body for a 409, carrying enough for the UI to name the holder."""
    identity = steam_account_id_identity(holder)
    label = user_display_name(holder)
    username = identity["username"]
    if username and username != label:
        label = f"{label} (@{username})"
    return {
        "code": "steam_account_id_taken",
        "error": f"Friend ID {steam_account_id} is already assigned to {label}.",
        "conflict": identity,
    }


def _require_id(user: CustomUser) -> int:
    if user.steam_account_id is None:
        raise ValueError("User has no Friend ID")
    return user.steam_account_id


def _apply_verification(user: CustomUser, values: dict[str, Any]) -> None:
    snapshot = user.__dict__.setdefault("_steam_snapshot", {})
    for attname in _VERIFICATION_ATTNAMES:
        setattr(user, attname, values[attname])
        snapshot[attname] = values[attname]
    for cached in ("steam_account_verified_by", "steam_account_verified_org"):
        user._state.fields_cache.pop(cached, None)


def _log_change(
    user: CustomUser, actor: CustomUser | None, org_id: int | None, verified: bool
) -> None:
    log.info(
        "steam_account_verification_changed",
        system="user",
        subsystem="steam",
        user_id=user.pk,
        actor_id=actor.pk if actor is not None else None,
        org_id=org_id,
        verified=verified,
    )


def mark_steam_account_verified(
    user: CustomUser,
    actor: CustomUser,
    *,
    org_id: int | None,
    expected_id: int | None = None,
    save: bool = True,
) -> bool:
    """Record that actor vouches for the user's current Friend ID.

    Returns False when the ID no longer matches expected_id. An already
    verified ID keeps its original verifier, time and org.
    """
    current_id = _require_id(user)
    expected = current_id if expected_id is None else expected_id

    if not save:
        if current_id != expected:
            return False
        snapshot = user.__dict__.get("_steam_snapshot", {})
        if user.steam_account_verified and snapshot.get("steam_account_id") == (
            current_id
        ):
            return True
        user.steam_account_verified_at = timezone.now()
        user.steam_account_verified_by = actor
        user.steam_account_verified_org_id = org_id
        _log_change(user, actor, org_id, True)
        return True

    values: dict[str, Any] = {
        "steam_account_verified_at": timezone.now(),
        "steam_account_verified_by_id": actor.pk,
        "steam_account_verified_org_id": org_id,
    }
    updated = CustomUser.objects.filter(
        pk=user.pk,
        steam_account_id=expected,
        steam_account_verified_at__isnull=True,
    ).update(**values)
    if not updated:
        row = (
            CustomUser.objects.nocache()
            .filter(pk=user.pk, steam_account_id=expected)
            .values(*_VERIFICATION_ATTNAMES)
            .first()
        )
        if row is None or row["steam_account_verified_at"] is None:
            return False
        _apply_verification(user, row)
        return True
    _apply_verification(user, values)
    invalidate_after_commit(user)
    _log_change(user, actor, org_id, True)
    return True


def clear_steam_account_verification(
    user: CustomUser,
    *,
    expected_id: int | None = None,
    save: bool = True,
    actor: CustomUser | None = None,
) -> bool:
    """Drop any vouching for the user's current Friend ID (compare-and-set)."""
    current_id = _require_id(user)
    expected = current_id if expected_id is None else expected_id
    values: dict[str, Any] = dict.fromkeys(_VERIFICATION_ATTNAMES)

    if not save:
        if current_id != expected:
            return False
        was_verified = user.steam_account_verified
        user.steam_account_verified_at = None
        user.steam_account_verified_by = None
        user.steam_account_verified_org = None
        if was_verified:
            _log_change(user, actor, None, False)
        return True

    updated = CustomUser.objects.filter(pk=user.pk, steam_account_id=expected).update(
        **values
    )
    if not updated:
        return False
    _apply_verification(user, values)
    invalidate_after_commit(user)
    _log_change(user, actor, None, False)
    return True


def steam_verification_payload(
    user: CustomUser, *, viewer: CustomUser
) -> dict[str, Any]:
    account_id = user.steam_account_id
    org = user.steam_account_verified_org if user.steam_account_verified else None
    return {
        "steam_account_id": account_id,
        "steam_account_verified": user.steam_account_verified,
        "steam_account_verified_at": user.steam_account_verified_at,
        "steam_account_verified_org_name": org.name if org is not None else None,
        "steam_account_exists_checked": user.steam_account_exists_checked_at
        is not None,
        "steam_profile_url": (
            None
            if account_id is None
            else "https://steamcommunity.com/profiles/"
            f"{account_id + CustomUser.STEAM_ID_64_BASE}"
        ),
        "dotabuff_url": (
            None
            if account_id is None
            else f"https://www.dotabuff.com/players/{account_id}"
        ),
        "can_verify": can_verify_steam_account(viewer, user) is not None,
    }
