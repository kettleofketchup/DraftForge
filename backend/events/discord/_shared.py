"""Shared helpers for the Discord signup dispatcher and per-game providers.

Factored out of ``handlers.py`` so the thin dispatcher (``handlers.py``) and the
per-game handler providers (``events/discord/providers/``) share one copy of
org-user resolution, event loading, logging, the dedupe check, and the
direct-signup happy path.

Load-bearing invariant: every ``from events.services import ...`` stays
**function-local**. The package cycle
``events.services -> events.discord(__init__) -> handlers`` is broken by
deferring those imports to call time; a top-level import here re-introduces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discordbot.models import DiscordEventLog
from events.constants import SignupStatus
from events.models import Event, EventSignup
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser
    from org.models import OrgUser

log = get_logger(__name__)


def _steam_friend_id_prefill(org_user: OrgUser) -> str:
    """Steam friend id from either game profile.

    One Steam account backs both games, so a Deadlock signup prefills from a
    known Dota friend id and vice versa. Splitting the handlers per game
    (#274) dropped this cross-game fallback; keep it in one place.
    """
    for attr in ("dota_profile", "deadlock_profile"):
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        if value:
            return value
    return ""


def _log_interaction(
    event_id: int,
    action: str,
    discord_user_id: str = "",
    discord_username: str = "",
    success: bool = True,
    error_message: str = "",
) -> None:
    """Log a Discord interaction (best-effort; surface failures via structlog)."""
    try:
        DiscordEventLog.log_interaction(
            event_id, action, discord_user_id, discord_username, success, error_message
        )
    except Exception as e:
        log.error(
            "discord_event_log_write_failed",
            system="discord",
            subsystem="interaction",
            kind="interaction",
            action=action,
            event_id=event_id,
            error=str(e),
            exc_info=True,
        )


def _log_signup(
    event_id: int,
    action: str,
    discord_user_id: str = "",
    discord_username: str = "",
    success: bool = True,
    error_message: str = "",
) -> None:
    """Log a signup action (best-effort; surface failures via structlog)."""
    try:
        DiscordEventLog.log_signup(
            event_id, action, discord_user_id, discord_username, success, error_message
        )
    except Exception as e:
        log.error(
            "discord_event_log_write_failed",
            system="discord",
            subsystem="interaction",
            kind="signup",
            action=action,
            event_id=event_id,
            error=str(e),
            exc_info=True,
        )


def _load_event(
    event_id: int,
    *,
    select_related: tuple[str, ...] = ("organization",),
) -> Event | None:
    """Load an Event with the given select_related, or None if it doesn't exist.

    Callers own the not-found response shape (it differs per endpoint).
    """
    try:
        return Event.objects.select_related(*select_related).get(pk=event_id)
    except Event.DoesNotExist:
        return None


def _get_org_user(
    event: Event,
    discord_user_id: str,
    discord_username: str | None = None,
) -> tuple[OrgUser | None, CustomUser | None]:
    """Look up or create OrgUser for the event's org + Discord user.

    If no CustomUser exists with this Discord ID, a "phantom" placeholder is
    auto-created using the Discord username. A button click only carries a
    Discord ID — it can't run the OAuth pipeline — so the phantom holds the
    signup until the person logs in, at which point the social-auth pipeline
    reclaims this exact row by discordId (see app/pipelines.py). The phantom is
    a normal, immediately-loginable account — no restrictions.

    Returns (org_user, user) or (None, None).
    """
    from django.db import IntegrityError, transaction

    from app.models import CustomUser, PositionsModel
    from events.services import resolve_or_create_org_user

    discord_id_str = str(discord_user_id)

    # 1) Primary: an account already linked to this Discord ID.
    user = CustomUser.objects.filter(discordId=discord_id_str).first()

    # 2) Discord usernames are globally unique, so an existing *unclaimed*
    #    account with this username is the same person. Claim it for this
    #    Discord ID instead of creating a duplicate (and instead of mangling
    #    the username, which would later collide when the OAuth login writes
    #    the real handle back in save_discord).
    if user is None and discord_username:
        candidate = CustomUser.objects.filter(username=discord_username).first()
        if candidate is not None and not candidate.discordId:
            candidate.discordId = discord_id_str
            try:
                with transaction.atomic():
                    candidate.save(update_fields=["discordId"])
                user = candidate
            except IntegrityError:
                # A concurrent click/login claimed this discordId first —
                # adopt that row instead of propagating a 500.
                user = CustomUser.objects.filter(discordId=discord_id_str).first()

    # 3) Otherwise create a fresh account keyed by the unique Discord handle.
    if user is None:
        username = discord_username or f"discord_{discord_id_str}"
        positions = PositionsModel.objects.create()
        new_user = CustomUser(
            username=username,
            discordId=discord_id_str,
            nickname=discord_username or username,
            positions=positions,
        )
        try:
            with transaction.atomic():
                new_user.save()
            user = new_user
        except IntegrityError:
            # Lost a race (a concurrent click or login created the row first),
            # rather than crash on the unique discordId/username constraint.
            positions.delete()
            user = CustomUser.objects.filter(discordId=discord_id_str).first()
            if user is None:
                # Handle is held by a different Discord identity (stale rename):
                # fall back to an id-based username, which is always unique.
                fallback_positions = PositionsModel.objects.create()
                user = CustomUser.objects.create(
                    username=f"discord_{discord_id_str}",
                    discordId=discord_id_str,
                    nickname=discord_username or f"discord_{discord_id_str}",
                    positions=fallback_positions,
                )

    org_user = resolve_or_create_org_user(user, event.organization)
    return org_user, user


def _existing_active_signup(event: Event, user: CustomUser) -> EventSignup | None:
    """Return a non-cancelled/rejected/tentative signup for this user, if any.

    Tentative can upgrade to a full signup, so it is excluded from the dedupe
    guard alongside cancelled/rejected.
    """
    return (
        EventSignup.objects.filter(event=event, user=user)
        .exclude(
            status__in=[
                SignupStatus.CANCELLED,
                SignupStatus.REJECTED,
                SignupStatus.TENTATIVE,
            ]
        )
        .first()
    )


def _direct_signup(event: Event, user: CustomUser) -> dict[str, str]:
    """process_rsvp happy path: persist + log signup_persisted, return dict.

    Raises ValueError on rejection so callers can attach endpoint-specific
    failure logging. notify_signup_changed is dispatched by _create_signup's
    on_commit hook — do NOT call it directly or the embed updates twice.
    """
    from events.services import process_rsvp

    signup = process_rsvp(event, user)
    log.info(
        "signup_persisted",
        system="discord",
        subsystem="interaction",
        signup_id=signup.pk,
        signup_status=signup.status,
    )
    return {"action": "signed_up", "status": signup.status}
