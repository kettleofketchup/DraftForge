from typing import Any

from django.contrib.auth import get_user_model

from telemetry.logging import get_logger

from .models import CustomUser, PositionsModel

User = get_user_model()

log = get_logger(__name__)


def save_discord(
    strategy: Any,
    details: Any,
    user: CustomUser | None = None,
    is_new: bool = False,
    *args: Any,
    **kwargs: Any,
) -> dict:
    from app.discord_accounts import merge_discord_accounts

    # save_discord runs after create_user, so user is always present here;
    # guard makes the None-path explicit and narrows the type for the body.
    if user is None:
        raise ValueError("save_discord requires an authenticated user")

    social_auth = user.social_auth.filter(provider="discord").first()
    discordId = social_auth.extra_data["id"]
    avatar = social_auth.extra_data["avatar"]
    discordUsername = social_auth.extra_data["username"]
    log.info(
        "discord_social_save",
        system="auth",
        subsystem="social",
        user_id=user.pk,
        discord_id=discordId,
        discord_username=discordUsername,
    )

    # Defense-in-depth: a Discord *button* signup may have already created a
    # separate account holding this discordId (unique). If so, fold this
    # freshly social-linked row into that account and continue as it, instead
    # of crashing with `IntegrityError: UNIQUE constraint failed: discordId`.
    # associate_by_discord_id reclaims it before create_user in the common case;
    # this covers logins where a prior failed attempt left a duplicate behind.
    conflict = (
        CustomUser.objects.filter(discordId=str(discordId)).exclude(pk=user.pk).first()
    )
    if conflict:
        merge_discord_accounts(keep=conflict, drop=user)
        user = conflict

    # Discord usernames are globally unique, so any *other* row still holding
    # this handle is the same person (e.g. a legacy un-reclaimed account). Fold
    # the unclaimed one in before writing the handle, so we can't hit
    # `UNIQUE constraint failed: username`.
    username_owner = (
        CustomUser.objects.filter(username=discordUsername).exclude(pk=user.pk).first()
    )
    if username_owner is not None and not username_owner.discordId:
        merge_discord_accounts(keep=user, drop=username_owner)
        username_owner = None

    # Only create positions if user doesn't have any (preserve existing positions!)
    if not user.positions_id:
        position = PositionsModel.objects.create()
        user.positions = position

    user.avatar = avatar
    user.discordId = discordId
    user.discordUsername = discordUsername
    # Leave the username untouched only in the pathological case where a
    # *different* Discord identity still owns the handle (stale rename).
    if username_owner is None:
        user.username = discordUsername
    user.save()
    # Return the (possibly merged) user so the rest of the pipeline and the
    # login session use the reclaimed account.
    return {"user": user}


def associate_by_discord_id(
    backend: Any = None,
    uid: Any = None,
    user: CustomUser | None = None,
    response: Any = None,
    details: Any = None,
    *args: Any,
    **kwargs: Any,
) -> dict | None:
    """Reclaim an existing CustomUser that already holds this Discord ID.

    Runs before `create_user` so a login adopts the row a Discord *button*
    signup created (which carries `discordId` but no social-auth link) instead
    of creating a duplicate that then collides on the unique `discordId` in
    `save_discord`.

    The Discord ID is the pipeline `uid` (set by `social_uid` from the OAuth
    `response`), NOT `details` — the old code read `details.get("id")`, which is
    always empty for the Discord backend, so this step never matched.
    """
    if user:
        return None  # Already authenticated or linked by an earlier step.

    discord_id = uid or (response or {}).get("id") or (details or {}).get("id")
    if not discord_id:
        return None

    existing_user = User.objects.filter(discordId=str(discord_id)).first()
    if existing_user:
        log.info(
            "discord_account_reclaimed",
            system="auth",
            subsystem="social",
            user_id=existing_user.pk,
            discord_id=discord_id,
        )
        return {"user": existing_user}
    return None


def associate_by_discord_username(
    backend: Any,
    details: Any,
    user: CustomUser | None = None,
    *args: Any,
    **kwargs: Any,
) -> dict | None:
    """
    Connect to a user if their discord username matches an existing user.
    `username` is the Discord username from the provider.
    """
    if user:
        return None  # Already authenticated or linked

    discordUsername = details.get("username")
    log.debug(
        "discord_username_lookup",
        system="auth",
        subsystem="social",
        discord_username=discordUsername,
    )
    if not discordUsername:
        return None

    try:
        existing_user = User.objects.get(username=discordUsername)
        log.info(
            "discord_user_matched",
            system="auth",
            subsystem="social",
            match_by="username",
            user_id=existing_user.pk,
        )
        return {"user": existing_user}
    except User.DoesNotExist:
        pass

    try:
        existing_user = User.objects.get(discordUsername=discordUsername)
        log.info(
            "discord_user_matched",
            system="auth",
            subsystem="social",
            match_by="discord_username",
            user_id=existing_user.pk,
        )
        return {"user": existing_user}
    except User.DoesNotExist:
        return None
