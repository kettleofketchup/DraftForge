"""The player's Steam Friend ID, stored once on ``CustomUser.steam_account_id``."""

from __future__ import annotations

from typing import Final

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from app.steam_accounts import steam_account_id_holder
from events.models import Event
from telemetry.logging import get_logger

log = get_logger(__name__)

# Steam account IDs are unsigned 32-bit; 0 is never assigned.
STEAM_ACCOUNT_ID_RANGE: Final[range] = range(1, 2**32)
FRIEND_ID_MAX_LENGTH: Final[int] = 20


def _duplicate_error(account_id: int) -> ValidationError:
    return ValidationError(
        f"Friend ID {account_id} is already registered to another account. "
        f"Contact an admin or login to {settings.SITE_URL} to claim it.",
        code="duplicate_friend_id",
    )


def validate_friend_id(fid: str | None, user: CustomUser) -> int | None:
    """The Friend ID to store on ``user``, or None when nothing changes.

    Blank input and the user's current ID are no-ops. Raises ValidationError
    for a malformed ID, a different ID than the one already set, or an ID
    another user holds.
    """
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
    if user.steam_account_id == account_id:
        return None
    if user.steam_account_id is not None:
        raise ValidationError(
            f"Your Friend ID is already set to {user.steam_account_id}; "
            "contact an admin to change it.",
            code="friend_id_already_set",
        )
    if steam_account_id_holder(account_id, exclude_pk=user.pk) is not None:
        raise _duplicate_error(account_id)
    return account_id


def claim_friend_id(
    user: CustomUser, fid: str | None, *, event: Event | None = None
) -> int | None:
    """Validate ``fid`` and store it on an empty ``user.steam_account_id``.

    Returns the stored ID, or None when nothing was written.
    """
    account_id = validate_friend_id(fid, user)
    if account_id is None:
        return None
    try:
        with transaction.atomic():
            user.steam_account_id = account_id
            user.save(update_fields=["steam_account_id", "steamid"])
    except IntegrityError as exc:
        user.refresh_from_db(fields=["steam_account_id", "steamid"])
        raise _duplicate_error(account_id) from exc
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
    )
    return account_id
