import calendar
import datetime
import re
from collections.abc import Collection
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser, GameType, PositionsModel, Team, Tournament
from discordbot.models import DiscordEvent, DiscordEventMsgSignup, DiscordMessageLog
from draft.services.team import apply_draft_options
from events.admission import NOT_ACCEPTING_MESSAGE, ensure_self_serve
from events.capacity import has_free_seat, lock_event, seat_holding_statuses
from events.constants import (
    EVENT_REOPEN_TRANSITIONS,
    EVENT_RESTART_TRANSITIONS,
    REGISTERED_SIGNUP_STATUSES,
    ActorRole,
    Commitment,
    EventState,
    RepeatFrequency,
    SignupOpenMode,
    SignupStatus,
    SignupType,
)
from events.discord import (
    notify_create_discord_event,
    notify_mark_interested,
    notify_new_event,
    notify_signup_changed,
)
from events.eligibility import (
    EligibilityResult,
    claim_friend_id,
    clear_eligibility,
    eligibility_values,
    evaluate_signup,
    refresh_unmet_requirements,
    stamp_eligibility,
    validate_friend_id,
)
from events.ledger import SignupActor
from events.models import (
    DiscordEventConfigMixin,
    DiscordTournamentConfigMixin,
    DotaLobbyConfigMixin,
    Event,
    EventConfigMixin,
    EventRepeater,
    EventSignup,
    EventTeam,
    TournamentTemplateMixin,
)
from events.ready_check_constants import (
    DROPPED_SIGNUP_MESSAGE,
    REMOVED_SIGNUP_STATUSES,
)
from events.reopen import ReopenNotPermitted, reopen_event
from events.roster import (
    RosterPhase,
    RosterSyncResult,
    joins_roster,
    leaving_statuses,
    roster_phase,
    roster_statuses,
    start_phase,
    team_bound_user_pks,
)
from events.schemas import DotaModalConfig
from events.signup_schedule import SIGNUP_OPEN_POLICY_FIELDS, apply_signup_open_policy
from events.tasks import delete_discord_scheduled_event
from lobby.passwords import PasswordMode, generate_password
from org.membership import resolve_or_create_org_user
from org.mmr import game_for_event
from org.mmr_official import apply_official_org_mmr
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile
from org.standing import api as standing
from org.standing.cache import StandingCache
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from discordbot.models import DiscordEvent
    from events.schemas import SignupInputPatch

logger = get_logger(__name__)
log = get_logger(__name__)


RANK_STATUS_DISALLOWED_MESSAGES = {
    "active": "This event does not accept active MMR signups.",
    "previous": "This event does not accept previous-rank signups.",
    "never": "This event does not accept Battle Cup–only signups.",
}

SCREENSHOT_URL_RE = re.compile(r"^https?://.+\.(png|jpe?g|webp)(\?.*)?$", re.IGNORECASE)
SCREENSHOT_BAD_URL_MESSAGE = "Screenshot must be a direct .png/.jpg/.jpeg/.webp URL."


def clear_signup_dedup_state(event_id: int) -> dict[str, int]:
    """Reset the dedup gates that block recreating a Discord signup post.

    Two gates need to flip so the next sync_discord_events run treats the
    event as needing a fresh signup post:
      - DiscordEventMsgSignup.has_posted=True → False (drops the event from
        the `events_with_signup_post` dedup set)
      - DiscordMessageLog rows with source=event_announcement, success=True
        → success=False (drops it from the `existing_logs` dedup set)

    Called by both auto-recovery on 404 Unknown Message AND the admin "Repost"
    button. Cacheops needs explicit invalidation here because .update() bypasses
    save signals and the signup-message model is cached. Use
    invalidate_after_commit so this is safe whether or not the caller wraps
    us in a transaction.atomic (fires immediately in autocommit; defers to
    on_commit when nested in a transaction).

    Returns a dict with the counts of rows changed.
    """

    affected_signups = list(
        DiscordEventMsgSignup.objects.filter(event_id=event_id, has_posted=True)
    )
    signup_rows_cleared = len(affected_signups)
    DiscordEventMsgSignup.objects.filter(event_id=event_id, has_posted=True).update(
        has_posted=False
    )
    for row in affected_signups:
        row.refresh_from_db()
        invalidate_after_commit(row)

    message_log_rows_cleared = DiscordMessageLog.objects.filter(
        source="event_announcement", source_id=event_id, success=True
    ).update(success=False)

    return {
        "signup_rows_cleared": signup_rows_cleared,
        "message_log_rows_cleared": message_log_rows_cleared,
    }


def _validate_screenshot_url(url: str | None) -> None:
    if url and not SCREENSHOT_URL_RE.match(url):
        raise ValidationError(SCREENSHOT_BAD_URL_MESSAGE, code="screenshot_bad_url")


def check_requirements(event: Event, user: CustomUser) -> bool:
    """Check if user meets event confirmation requirements."""
    return evaluate_signup(event, user, for_staff_placement=True).clean


def _first_fields_carry(existing: EventSignup | None) -> dict[str, Any]:
    if existing is None:
        return {}
    return {
        "first_signed_up_at": existing.first_signed_up_at,
        "first_commitment": existing.first_commitment,
        "first_rsvp_class": existing.first_rsvp_class,
    }


def _decide_signup_status(event: Event, result: EligibilityResult) -> SignupStatus:
    """Status for a signup taking a seat. Auto-approve events approve (or
    confirm) eligible players and hold the rest for staff; manual-approval
    events leave everyone at RSVP."""
    if not event.auto_approve:
        return SignupStatus.RSVP
    if result.approval or result.blocking:
        return SignupStatus.PENDING_APPROVAL
    if event.auto_confirm:
        return SignupStatus.CONFIRMED
    return SignupStatus.APPROVED


def _roster_add_if_joins(signup: EventSignup) -> None:
    """Add the player when their status joins the roster in the current phase.
    Never removes: a status outside the roster leaves existing membership alone."""
    if joins_roster(signup.event, signup.status):
        add_user_to_tournament(signup.event, signup.user)


def _log_kept_on_team(
    event: Event, tournament: Tournament, user_id: int, **context: str
) -> None:
    log.info(
        "event_roster_sync_skipped_team_member",
        system="events",
        subsystem="services",
        event_id=event.pk,
        tournament_id=tournament.pk,
        user_id=user_id,
        **context,
    )


def _roster_remove_if_left(signup: EventSignup) -> None:
    """Remove the player when their status no longer joins the roster. This
    is an explicit staff or player action, so it also drops them from their
    team; only the bulk sync in sync_event_roster keeps team members."""
    if joins_roster(signup.event, signup.status):
        return
    remove_user_from_tournament(signup.event, signup.user)


@transaction.atomic
def _create_signup(
    event: Event,
    user: CustomUser,
    event_team: EventTeam | None = None,
    *,
    for_staff_placement: bool = False,
) -> EventSignup:
    """Internal: create a signup with no state check.

    Handles existing-signup detection, waitlist placement, auto-approve / auto-confirm,
    tournament addition, and notify hooks. State authorization is the caller's job.

    INVARIANT: invalidate_after_commit MUST be registered before any transaction.on_commit
    notify hook. Notify handlers may re-query, and reading through a stale cache would
    re-warm it with stale data.
    """
    existing = EventSignup.objects.filter(event=event, user=user).first()
    carry = _first_fields_carry(existing)
    if existing:
        logger.info(
            "signup_existing_found",
            system="events",
            subsystem="services",
            user_id=user.pk,
            event_id=event.pk,
            status=existing.status,
            signup_id=existing.id,
        )
        if existing.status in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            existing.delete()
            logger.info(
                "signup_cancelled_deleted",
                system="events",
                subsystem="services",
                user_id=user.pk,
                event_id=event.pk,
            )
        elif existing.status == SignupStatus.TENTATIVE:
            existing.delete()
            logger.info(
                "signup_tentative_upgraded",
                system="events",
                subsystem="services",
                user_id=user.pk,
                event_id=event.pk,
            )
        elif existing.status == SignupStatus.DROPPED:
            raise ValueError(DROPPED_SIGNUP_MESSAGE)
        else:
            raise ValueError("User has already signed up for this event.")

    signup_type = SignupType.TEAM if event_team else SignupType.USER
    result = evaluate_signup(event, user, for_staff_placement=for_staff_placement)
    eligibility = eligibility_values(result)

    if not has_free_seat(lock_event(event)):
        max_pos = (
            EventSignup.objects.filter(event=event, status=SignupStatus.WAITLISTED)
            .order_by("-waitlist_position")
            .values_list("waitlist_position", flat=True)
            .first()
        ) or 0
        signup = EventSignup.objects.create(
            event=event,
            user=user,
            event_team=event_team,
            signup_type=signup_type,
            status=SignupStatus.WAITLISTED,
            waitlist_position=max_pos + 1,
            **eligibility,
            **carry,
        )
        invalidate_after_commit(event)
        log.info(
            "signup_post_commit_hooks_scheduled",
            system="events",
            subsystem="services",
            signup_id=signup.pk,
            event_id=event.pk,
        )
        transaction.on_commit(lambda: notify_signup_changed(event))
        return signup

    status = _decide_signup_status(event, result)
    signup = EventSignup.objects.create(
        event=event,
        user=user,
        event_team=event_team,
        signup_type=signup_type,
        status=status,
        **eligibility,
        **carry,
    )
    _roster_add_if_joins(signup)
    invalidate_after_commit(event)
    log.info(
        "signup_post_commit_hooks_scheduled",
        system="events",
        subsystem="services",
        signup_id=signup.pk,
        event_id=event.pk,
    )
    transaction.on_commit(lambda: notify_signup_changed(event))
    if status in (SignupStatus.CONFIRMED, SignupStatus.APPROVED):
        transaction.on_commit(lambda: notify_mark_interested(event, user.pk))
    return signup


def process_rsvp(
    event: Event, user: CustomUser, event_team: EventTeam | None = None
) -> EventSignup:
    """Public-path signup. Self-serve admission applies (events.admission)."""
    log.info(
        "process_rsvp_started",
        system="events",
        subsystem="services",
        event_id=event.pk,
        user_id=user.pk,
    )
    ensure_self_serve(event, user, intent=Commitment.MAIN)
    signup = _create_signup(event, user, event_team=event_team)
    # Defer signup_created log until the outermost atomic commits — otherwise
    # rollback paths produce a log claiming a signup that doesn't persist.
    transaction.on_commit(
        lambda: log.info(
            "signup_created",
            system="events",
            subsystem="services",
            signup_id=signup.pk,
            status=signup.status,
            event_id=event.pk,
            user_id=user.pk,
        )
    )
    return signup


@transaction.atomic
def create_tentative_signup(
    event: Event, user: CustomUser, *, actor: SignupActor | None = None
) -> EventSignup:
    """Create a TENTATIVE EventSignup, upgrading any active signup to tentative.

    Funnel point for both the DRF action and the Discord tentative button.

    Behavior:
      - Self-serve admission applies (events.admission).
      - If existing TENTATIVE signup -> raise ValueError (already tentative).
      - If existing DROPPED signup -> raise ValueError; the row is kept.
      - If existing active signup (RSVP/APPROVED/CONFIRMED/PENDING/WAITLISTED)
        -> cancel it, delete the row, then create a fresh TENTATIVE.
      - If existing CANCELLED/REJECTED row -> delete it, create fresh TENTATIVE.
      - notify_signup_changed is dispatched once via on_commit
        (cancel_signup also schedules one when invoked; we skip registering
        a duplicate in that case).
    """
    ensure_self_serve(event, user, intent=Commitment.MAYBE)

    existing = EventSignup.objects.filter(event=event, user=user).first()
    carry = _first_fields_carry(existing)
    notify_scheduled_by_cancel = False
    if existing:
        if existing.status == SignupStatus.TENTATIVE:
            raise ValueError("Already marked as tentative")
        if existing.status == SignupStatus.DROPPED:
            raise ValueError(DROPPED_SIGNUP_MESSAGE)
        if existing.status not in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            cancel_signup(existing, actor=actor)
            notify_scheduled_by_cancel = True
        EventSignup.objects.filter(pk=existing.pk).delete()

    signup = EventSignup.objects.create(
        event=event, user=user, status=SignupStatus.TENTATIVE, **carry
    )
    # invalidate_after_commit is on_commit-aware internally; do NOT wrap.
    invalidate_after_commit(signup, event)
    if not notify_scheduled_by_cancel:
        # notify_signup_changed is NOT on_commit-aware; wrap explicitly.
        transaction.on_commit(lambda: notify_signup_changed(event))
    return signup


@transaction.atomic
def decline_signup(
    event: Event, user: CustomUser, *, actor: SignupActor | None = None
) -> EventSignup:
    """Record that a user declined an event.

    Cancels an existing active/tentative signup, or creates a CANCELLED row so
    a user who never signed up still appears in the Declined list.
    Raises ValueError if the user has already declined.
    """
    existing = EventSignup.objects.filter(event=event, user=user).first()
    if existing:
        if existing.status in REMOVED_SIGNUP_STATUSES:
            raise ValueError("Already declined")
        return cancel_signup(existing, actor=actor)

    signup = EventSignup.objects.create(
        event=event, user=user, status=SignupStatus.CANCELLED
    )
    invalidate_after_commit(signup, event)
    transaction.on_commit(lambda: notify_signup_changed(event))
    return signup


def apply_signup_input(
    *, org_user: "OrgUser", event: Event, patch: "SignupInputPatch"
) -> "PlayerDotaProfile | None":
    """Idempotently write any provided fields onto the OrgUser's PlayerDotaProfile.

    Used by both the web `/signup/` endpoint and the Discord adapters so the
    write path is identical. Per-field branches:
      - steam_account_id: validate_friend_id (digits, range, site-wide
        uniqueness, never replaces a set ID), then fills an empty
        CustomUser.steam_account_id.
      - positions: priorities dict or list[int] of roles; writes pos_1..pos_5
        booleans and CustomUser.positions priorities.
      - rank_status: validated against event.allow_* flags on Dota events.
      - rank_medal, battle_cup_tier: written as-is.
      - rank_screenshot, battlecup_screenshot: URL shape validated, then written.

    Contract:
      - Fields not in `patch` are not touched (partial-patch semantics).
      - Multiple calls with the same `patch` are safe (idempotent).
      - Returns the PlayerDotaProfile when `patch` had any set fields, or
        None if `patch` was empty.
      - Cacheops invalidation is registered via invalidate_after_commit,
        which schedules via transaction.on_commit when a transaction is
        active and fires immediately otherwise. Do NOT wrap in an outer
        transaction.on_commit.
    """
    set_fields = patch.model_dump(exclude_unset=True)
    if not set_fields:
        return None

    user = org_user.user
    if "steam_account_id" in set_fields:
        validate_friend_id(set_fields["steam_account_id"], user)
    profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=org_user)
    if "positions" in set_fields:
        # Two accepted input shapes (normalized to per-role priorities here):
        #   - dict {carry, mid, offlane, soft_support, hard_support} each 0..5
        #     (web modal — preserves real user-picked priorities)
        #   - list[int] in {1..5} (Discord adapter): slot order encodes
        #     priority. The Discord UI presents three sequential Selects
        #     ("1st choice / 2nd choice / 3rd choice") that emit role numbers
        #     in the order picked, e.g. [1, 3, 5] means "carry is 1st pick,
        #     offlane is 2nd, hard support is 3rd". We map list index + 1 →
        #     priority (Favorite → Can play → If team needs → I would rather
        #     not → Least Favorite), capping at 5. Duplicate role numbers
        #     keep their earliest slot.
        # Mapping role → pos_N: carry=1, mid=2, offlane=3, soft_support=4,
        # hard_support=5. PlayerDotaProfile.pos_N stays binary; the priorities
        # land on CustomUser.positions (PositionsModel).
        raw = set_fields["positions"]
        if isinstance(raw, dict):
            priorities = {
                "carry": int(raw.get("carry", 0) or 0),
                "mid": int(raw.get("mid", 0) or 0),
                "offlane": int(raw.get("offlane", 0) or 0),
                "soft_support": int(raw.get("soft_support", 0) or 0),
                "hard_support": int(raw.get("hard_support", 0) or 0),
            }
        else:
            _ROLE_BY_NUM = {
                1: "carry",
                2: "mid",
                3: "offlane",
                4: "soft_support",
                5: "hard_support",
            }
            priorities = {
                "carry": 0,
                "mid": 0,
                "offlane": 0,
                "soft_support": 0,
                "hard_support": 0,
            }
            for slot_idx, role_num in enumerate(raw or []):
                role = _ROLE_BY_NUM.get(role_num)
                if role and priorities[role] == 0:
                    priorities[role] = min(slot_idx + 1, 5)

        # Derive per-org binary flags from priorities.
        profile.pos_1 = priorities["carry"] > 0
        profile.pos_2 = priorities["mid"] > 0
        profile.pos_3 = priorities["offlane"] > 0
        profile.pos_4 = priorities["soft_support"] > 0
        profile.pos_5 = priorities["hard_support"] > 0

        # Write priorities to the user's main PositionsModel so the
        # edit-profile page reflects them. Auto-create the row if missing
        # (matches CustomUser.save() default).
        user_positions = user.positions
        if user_positions is None:
            user_positions = PositionsModel.objects.create()
            user.positions = user_positions
        changed = False
        for role, rating in priorities.items():
            if getattr(user_positions, role) != rating:
                setattr(user_positions, role, rating)
                changed = True
        if changed:
            user_positions.save(
                update_fields=[
                    "carry",
                    "mid",
                    "offlane",
                    "soft_support",
                    "hard_support",
                ]
            )
            invalidate_after_commit(user_positions, user)
    if "rank_status" in set_fields:
        status = set_fields["rank_status"]
        if event.game_type == GameType.DOTA2 and not DotaModalConfig.from_event(
            event
        ).allows_rank_status(status):
            raise ValidationError(
                RANK_STATUS_DISALLOWED_MESSAGES[status],
                code="rank_status_disallowed",
            )
        profile.declare_rank(status)

    if "rank_medal" in set_fields:
        profile.rank_medal = set_fields["rank_medal"] or ""

    if "battle_cup_tier" in set_fields:
        profile.battle_cup_tier = set_fields["battle_cup_tier"]

    if "rank_screenshot" in set_fields:
        _validate_screenshot_url(set_fields["rank_screenshot"])
        profile.rank_screenshot = set_fields["rank_screenshot"] or ""

    if "battlecup_screenshot" in set_fields:
        _validate_screenshot_url(set_fields["battlecup_screenshot"])
        profile.battlecup_screenshot = set_fields["battlecup_screenshot"] or ""

    if "steam_account_id" in set_fields:
        claim_friend_id(user, set_fields["steam_account_id"], event=event)
    profile.save()
    invalidate_after_commit(profile, org_user, event)
    refresh_unmet_requirements(org_user)
    log.info(
        "signup_input_applied",
        system="events",
        subsystem="services",
        set_fields=list(set_fields.keys()),
        profile_id=profile.pk,
        org_user_id=org_user.pk,
    )
    return profile


def staff_add_signup(
    event: Event, user: CustomUser, event_team: EventTeam | None = None
) -> EventSignup:
    """Staff-path signup. Allowed during SIGNUPS_OPEN or ROLL_CALL."""
    if event.state not in (EventState.SIGNUPS_OPEN, EventState.ROLL_CALL):
        raise ValueError(NOT_ACCEPTING_MESSAGE)
    # Admin-added users join the organization so per-org data (MMR, history)
    # has somewhere to live before they're approved.
    if event.organization_id:
        resolve_or_create_org_user(user, event.organization)
    return _create_signup(event, user, event_team=event_team, for_staff_placement=True)


APPROVABLE_STATUSES = [
    SignupStatus.RSVP,
    SignupStatus.PENDING_APPROVAL,
    SignupStatus.WAITLISTED,
]


@transaction.atomic
def approve_signup(
    signup: EventSignup,
    mmr_override: int | None = None,
    actor: CustomUser | None = None,
) -> EventSignup:
    """Approve a signup, optionally setting the user's MMR."""
    if signup.status not in APPROVABLE_STATUSES:
        raise ValueError(f"Cannot approve signup in '{signup.status}' status.")

    if mmr_override is not None:
        if signup.event.organization_id is None:
            raise ValueError("Cannot set MMR for an event without an organization.")
        org_user = resolve_or_create_org_user(signup.user, signup.event.organization)
        apply_official_org_mmr(
            org_user,
            game_for_event(signup.event),
            mmr_override,
            actor=actor,
            source="event_approve",
            extra_log={"event_id": signup.event.pk},
            log_unchanged=True,
        )

    signup.status = SignupStatus.APPROVED
    signup.waitlist_position = None
    cleared = clear_eligibility(signup)
    signup.save(update_fields=["status", "waitlist_position", *cleared, "updated_at"])
    _roster_add_if_joins(signup)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def reject_signup(signup: EventSignup) -> EventSignup:
    """Reject a signup."""
    if signup.status in REMOVED_SIGNUP_STATUSES:
        raise ValueError(f"Cannot reject signup in '{signup.status}' status.")
    prior_status = signup.status
    signup.status = SignupStatus.REJECTED
    signup.save(update_fields=["status", "updated_at"])
    _roster_remove_if_left(signup)
    if prior_status in seat_holding_statuses(signup.event):
        _promote_from_waitlist(signup.event)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def confirm_signup(signup: EventSignup) -> EventSignup:
    """Confirm a signup (e.g., during roll call)."""
    if signup.status != SignupStatus.APPROVED:
        raise ValueError("Only approved signups can be confirmed.")
    signup.status = SignupStatus.CONFIRMED
    signup.save(update_fields=["status", "updated_at"])
    _roster_add_if_joins(signup)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def cancel_signup(
    signup: EventSignup, *, actor: SignupActor | None = None
) -> EventSignup:
    """Cancel a signup."""
    if signup.status in REMOVED_SIGNUP_STATUSES:
        raise ValueError(f"Cannot cancel signup in '{signup.status}' status.")
    prior_status = signup.status
    signup.status = SignupStatus.CANCELLED
    signup.save(update_fields=["status", "updated_at"])
    standing.on_signup_withdrawn(
        signup, prior_status=prior_status, by_member=_by_member(actor)
    )
    _roster_remove_if_left(signup)
    if prior_status in seat_holding_statuses(signup.event):
        _promote_from_waitlist(signup.event)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    # Log on commit, not on entry — same reason as signup_created in process_rsvp:
    # callers may roll back the outer transaction, in which case the cancellation
    # never persisted.
    transaction.on_commit(
        lambda: log.info(
            "signup_cancelled",
            system="events",
            subsystem="services",
            signup_id=signup.pk,
            prior_status=prior_status,
            event_id=signup.event_id,
            user_id=signup.user_id,
        )
    )
    return signup


def _by_member(actor: SignupActor | None) -> bool:
    return actor is not None and actor.role == ActorRole.MEMBER


def _promote_one(
    locked: Event, signup: EventSignup, *, cache: StandingCache
) -> EventSignup:
    signup.waitlist_position = None
    result = evaluate_signup(
        locked, signup.user, for_staff_placement=True, standing_cache=cache
    )
    stamped = stamp_eligibility(signup, result)
    signup.status = _decide_signup_status(locked, result)
    _roster_add_if_joins(signup)
    signup.save(update_fields=["status", "waitlist_position", *stamped, "updated_at"])
    invalidate_after_commit(signup)
    return signup


def _promote_from_waitlist(event: Event) -> list[EventSignup]:
    """Promote waitlisted signups into every free seat, in waitlist order as
    reordered by the org's standing tracks."""
    locked = lock_event(event)
    promoted: list[EventSignup] = []
    if has_free_seat(locked):
        candidates = list(
            EventSignup.objects.nocache()
            .filter(event=locked, status=SignupStatus.WAITLISTED)
            .select_related("user")
            .order_by("waitlist_position")
        )
        cache = StandingCache()
        for candidate in standing.promotion_order(locked, candidates, cache=cache):
            if not has_free_seat(locked):
                break
            promoted.append(_promote_one(locked, candidate, cache=cache))
    if promoted:
        invalidate_after_commit(locked)
    return promoted


@transaction.atomic
def unconfirm_signup(signup: EventSignup) -> EventSignup:
    """Revert a confirmed signup back to approved (e.g., during roll call adjustments)."""
    if signup.status != SignupStatus.CONFIRMED:
        raise ValueError("Only confirmed signups can be unconfirmed.")
    signup.status = SignupStatus.APPROVED
    signup.save(update_fields=["status", "updated_at"])
    _roster_remove_if_left(signup)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def demote_to_waitlist(signup: EventSignup) -> EventSignup:
    """Move an active signup to the end of the waitlist."""
    if signup.status in (*REMOVED_SIGNUP_STATUSES, SignupStatus.WAITLISTED):
        raise ValueError(f"Cannot demote signup in '{signup.status}' status.")
    max_pos = (
        EventSignup.objects.filter(
            event=signup.event, status=SignupStatus.WAITLISTED
        ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]
        or 0
    )
    signup.status = SignupStatus.WAITLISTED
    signup.waitlist_position = max_pos + 1
    signup.save(update_fields=["status", "waitlist_position", "updated_at"])
    _roster_remove_if_left(signup)
    invalidate_after_commit(signup, signup.event)
    transaction.on_commit(lambda: notify_signup_changed(signup.event))
    return signup


@transaction.atomic
def reinstate_signup(
    signup: EventSignup, *, for_staff_placement: bool = True
) -> EventSignup:
    """Bring a removed signup back into the active list.

    Behavior depends on event state:
      - signups_open: CANCELLED → the status a new signup would get
                      (``_decide_signup_status``), or WAITLISTED if full.
      - roll_call:    CANCELLED or REJECTED → APPROVED, so the player
                      reappears in the Awaiting Confirmation list and admins
                      can re-confirm without leaving the rollcall screen.
    """
    event = signup.event
    if event.state == "roll_call":
        if signup.status not in (SignupStatus.CANCELLED, SignupStatus.REJECTED):
            raise ValueError(
                "Only removed or rejected signups can be reinstated during roll call."
            )
        signup.status = SignupStatus.APPROVED
        signup.waitlist_position = None
        signup.commitment = Commitment.MAIN
        cleared = clear_eligibility(signup)
        signup.save(
            update_fields=[
                "status",
                "waitlist_position",
                "commitment",
                *cleared,
                "updated_at",
            ]
        )
        invalidate_after_commit(signup, event)
        transaction.on_commit(lambda: notify_signup_changed(event))
        return signup

    if signup.status != SignupStatus.CANCELLED:
        raise ValueError("Only cancelled signups can be reinstated.")
    if event.state != "signups_open":
        raise ValueError(NOT_ACCEPTING_MESSAGE)
    locked = lock_event(event)
    result = evaluate_signup(
        locked, signup.user, for_staff_placement=for_staff_placement
    )
    if not has_free_seat(locked):
        max_pos = (
            EventSignup.objects.filter(
                event=event, status=SignupStatus.WAITLISTED
            ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]
            or 0
        )
        signup.status = SignupStatus.WAITLISTED
        signup.waitlist_position = max_pos + 1
    else:
        signup.status = _decide_signup_status(locked, result)
        signup.waitlist_position = None
        _roster_add_if_joins(signup)
    signup.commitment = Commitment.MAIN
    stamped = stamp_eligibility(signup, result)
    signup.save(
        update_fields=[
            "status",
            "waitlist_position",
            "commitment",
            *stamped,
            "updated_at",
        ]
    )
    invalidate_after_commit(signup, event)
    transaction.on_commit(lambda: notify_signup_changed(event))
    return signup


# ---------------------------------------------------------------------------
# Tournament lifecycle
# ---------------------------------------------------------------------------

LOBBY_CONFIG_FIELDS = [
    "game_mode",
    "custom_game_name",
    "captains_draft_time",
    "lobby_steam_league_id",
    # dota_lobby settings (DotaLobbyConfigMixin) and the event's password.
    "dota_lobby_mode",
    "dota_lobby_launch",
    "dota_lobby_region",
    "discord_send_lobby_info",
    "dota_lobby_password",
]

DISCORD_TOURNAMENT_CONFIG_FIELDS = [
    "auto_create_hero_drafts",
    "discord_send_draft_link",
    "discord_send_herodraft_link",
]

EVENT_DRAFT_OPTIONS_FIELDS: dict[str, str] = {
    "draft_timer_enabled": "timer_enabled",
    "draft_grace_time_ms": "grace_time_ms",
    "draft_reserve_time_ms": "reserve_time_ms",
    "draft_timeout_action": "timeout_action",
    "hero_timer_enabled": "hero_timer_enabled",
    "hero_grace_time_ms": "hero_grace_time_ms",
    "hero_reserve_time_ms": "hero_reserve_time_ms",
}


def event_draft_option_values(event: Event | EventRepeater) -> dict[str, Any]:
    return {field: getattr(event, field) for field in EVENT_DRAFT_OPTIONS_FIELDS}


def changed_draft_option_fields(
    before: dict[str, Any], event: Event | EventRepeater
) -> frozenset[str]:
    after = event_draft_option_values(event)
    return frozenset(f for f, v in after.items() if before.get(f) != v)


def apply_event_draft_options(
    event: Event, tournament: Tournament, fields: Collection[str] | None = None
) -> None:
    names = EVENT_DRAFT_OPTIONS_FIELDS if fields is None else fields
    data = {EVENT_DRAFT_OPTIONS_FIELDS[f]: getattr(event, f) for f in names}
    if data:
        apply_draft_options(tournament, data)


@transaction.atomic
def create_tournament_for_event(event: Event) -> Tournament:
    """Create a future Tournament from event template fields. Returns Tournament."""
    tournament = Tournament.objects.create(
        name=event.tournament_name,
        league=event.tournament_league,
        tournament_type=event.tournament_type,
        game_type=event.game_type,
        draft_type=event.draft_type,
        people_per_team=event.people_per_team,
        number_of_teams=event.number_of_teams,
        date_played=event.tournament_date or event.scheduled_at,
        timezone=event.timezone,
        game_mode=event.game_mode,
        custom_game_name=event.custom_game_name,
        captains_draft_time=event.captains_draft_time,
        lobby_steam_league_id=event.lobby_steam_league_id,
        auto_create_hero_drafts=event.auto_create_hero_drafts,
        discord_send_draft_link=event.discord_send_draft_link,
        discord_send_herodraft_link=event.discord_send_herodraft_link,
        dota_lobby_mode=event.dota_lobby_mode,
        dota_lobby_launch=event.dota_lobby_launch,
        dota_lobby_region=event.dota_lobby_region,
        discord_send_lobby_info=event.discord_send_lobby_info,
        dota_lobby_password=event.dota_lobby_password,
        state="future",
    )
    apply_event_draft_options(event, tournament)
    event.tournament = tournament
    event.save(update_fields=["tournament", "updated_at"])
    invalidate_after_commit(event)
    return tournament


def ensure_discord_event(event: Event) -> "DiscordEvent | None":
    """Auto-create a DiscordEvent row if the org has a discord_server_id.

    This ensures the Discord tab works immediately after event creation
    without waiting for celery tasks to run.
    """
    org = event.organization
    if not org or not org.discord_server_id:
        return None

    de, created = DiscordEvent.objects.get_or_create(
        event=event,
        defaults={"guild_id": org.discord_server_id},
    )
    if created:
        logger.info(
            "discord_event_auto_created",
            system="events",
            subsystem="services",
            event_id=event.pk,
            guild_id=str(org.discord_server_id),
        )
    return de


def add_user_to_tournament(event: Event, user: CustomUser) -> None:
    """Add a user to the event's linked future tournament."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.users.add(user)
        invalidate_obj(event.tournament)


def remove_user_from_tournament(event: Event, user: CustomUser) -> None:
    """Remove a user from the event's linked future tournament."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.users.remove(user)
        invalidate_obj(event.tournament)


def finalize_event_tournament(event: Event) -> None:
    """Transition linked tournament from future to in_progress."""
    if event.tournament and event.tournament.state == "future":
        event.tournament.state = "in_progress"
        event.tournament.save(update_fields=["state"])
        invalidate_obj(event.tournament)


def sync_tournament_from_event(
    event: Event, changed_draft_fields: Collection[str] = ()
) -> dict[str, Any]:
    """Cascade event config changes to linked Tournament.

    Only the draft option fields in ``changed_draft_fields`` reach the
    tournament's DraftOptions, so options edited on the tournament survive
    unrelated event saves.

    Returns dict with 'synced' (bool) and 'warning' (str or None).
    """
    if not event.tournament:
        return {"synced": False, "warning": None}

    state = event.tournament.state
    if state == "future":
        event.tournament.name = event.tournament_name
        event.tournament.league = event.tournament_league
        event.tournament.tournament_type = event.tournament_type
        event.tournament.game_type = event.game_type
        event.tournament.draft_type = event.draft_type
        event.tournament.people_per_team = event.people_per_team
        event.tournament.number_of_teams = event.number_of_teams
        event.tournament.date_played = event.tournament_date or event.scheduled_at
        event.tournament.timezone = event.timezone
        for field in LOBBY_CONFIG_FIELDS + DISCORD_TOURNAMENT_CONFIG_FIELDS:
            setattr(event.tournament, field, getattr(event, field))
        event.tournament.save()
        apply_event_draft_options(event, event.tournament, changed_draft_fields)
        invalidate_obj(event.tournament)
        return {"synced": True, "warning": None}
    elif state == "in_progress":
        warning = "Tournament is in progress. Changes were saved to the event but not applied to the active tournament."
        if push_lobby_password_to_tournament(event):
            warning += " The new lobby password applies to lobbies created from now on."
        return {"synced": False, "warning": warning}
    else:
        return {
            "synced": False,
            "warning": "Tournament has already completed. Changes were saved to the event only.",
        }


@transaction.atomic
def restart_event_tournament(
    event: Event, *, actor: CustomUser | None = None, can_reopen: bool = False
) -> Tournament:
    """Delete existing tournament, create fresh one, reopen signups.

    Re-adds the SIGNUPS_OPEN roster: CONFIRMED, plus APPROVED when roll call
    is disabled (same rule as approve_signup). A completed or cancelled event
    needs ``can_reopen`` and goes through reopen_event, which takes back the
    host and helper points.
    """
    event = Event.objects.nocache().select_for_update().get(pk=event.pk)
    if not event.tournament:
        raise ValueError("No tournament to restart.")

    if event.state in EVENT_REOPEN_TRANSITIONS:
        if not can_reopen:
            raise ReopenNotPermitted(
                "Only an organization admin can restart a closed event."
            )
        if not reopen_event(event, actor=actor).reopened:
            raise ValueError("The event changed while restarting; try again.")
    elif event.state != EventState.SIGNUPS_OPEN:
        event.transition_state(
            EventState.SIGNUPS_OPEN, transitions=EVENT_RESTART_TRANSITIONS
        )

    old_tournament = event.tournament
    event.tournament = None
    event.save(update_fields=["tournament", "updated_at"])
    old_tournament.delete()

    create_tournament_for_event(event)
    return sync_event_roster(event, RosterPhase.SIGNUPS).tournament


@transaction.atomic
def sync_event_roster(
    event: Event, phase: RosterPhase | None = None
) -> RosterSyncResult:
    """Bring event.tournament.users in line with the roster rule for a phase.

    Creates the tournament if missing (#200). Adds every signup whose status
    joins the roster; removes signed-up users whose status left it, except
    members, captains and deputies of a team in the tournament, who are kept
    and reported. DROPPED players always leave. Users on the roster without a
    signup are left alone.
    Idempotent. M2M writes are not tracked by cacheops, so the tournament,
    the event and every touched user are invalidated on commit.
    """
    phase = phase or roster_phase(event)
    if event.tournament is None:
        create_tournament_for_event(event)
        event.refresh_from_db()
    tournament = event.tournament

    added = [
        signup.user
        for signup in EventSignup.objects.nocache()
        .filter(event=event, status__in=roster_statuses(event, phase))
        .select_related("user")
    ]
    tournament.users.add(*added)

    leaving = list(
        tournament.users.all()
        .nocache()
        .filter(
            event_signups__event=event,
            event_signups__status__in=leaving_statuses(event, phase),
        )
        .distinct()
    )
    team_bound = team_bound_user_pks(tournament) if leaving else set()
    kept_on_team = [user for user in leaving if user.pk in team_bound]
    removed = [user for user in leaving if user.pk not in team_bound]
    tournament.users.remove(*removed)
    for user in kept_on_team:
        _log_kept_on_team(event, tournament, user.pk, phase=str(phase))

    sync_fields: dict[str, object] = {
        "system": "events",
        "subsystem": "services",
        "event_id": event.pk,
        "tournament_id": tournament.pk,
        "phase": str(phase),
        "added_count": len(added),
        "removed_count": len(removed),
        "kept_on_team_count": len(kept_on_team),
    }
    if phase == RosterPhase.ROLL_CALL:
        log.info("event_roster_synced_on_roll_call", **sync_fields)
    else:
        log.info("event_tournament_roster_synced", **sync_fields)
    invalidate_after_commit(tournament, event, *added, *removed)
    return RosterSyncResult(
        tournament=tournament, added=added, removed=removed, kept_on_team=kept_on_team
    )


def ensure_tournament_with_signups(
    event: Event, phase: RosterPhase | None = None
) -> Tournament:
    """Self-heal before a tournament starts: create it if missing and sync its
    roster. Defaults to the start rule: confirmed only from roll call (#378),
    approved and confirmed when starting straight from signups."""
    return sync_event_roster(event, phase or start_phase(event)).tournament


@transaction.atomic
def cancel_event(event: Event, *, actor: CustomUser | None) -> Event:
    if event.tournament:
        tournament = event.tournament
        event.tournament = None
        event.save(update_fields=["tournament", "updated_at"])
        tournament.delete()
    event.transition_state(EventState.CANCELLED)
    event.refresh_from_db(from_queryset=Event.objects.nocache().all())
    standing.on_event_closed(event, cancelled=True, source="cancel", actor=actor)
    try:
        discord_event = event.discord_event
    except DiscordEvent.DoesNotExist:
        discord_event = None
    if discord_event is not None and discord_event.scheduled_event_id:
        guild_id = discord_event.guild_id
        scheduled_event_id = discord_event.scheduled_event_id
        transaction.on_commit(
            lambda: delete_discord_scheduled_event.delay(guild_id, scheduled_event_id)
        )
        # Clearing the id stops the 60s sync_discord_events resurrecting it.
        discord_event.scheduled_event_id = None
        discord_event.save(update_fields=["scheduled_event_id"])
        log.info(
            "event_cancel_discord_scheduled_event_deleted",
            system="events",
            subsystem="services",
            event_id=event.pk,
            guild_id=discord_event.guild_id,
        )
    return event


def teardown_event(event: Event, *, actor: CustomUser | None = None) -> None:
    """Delete an event and everything Discord/tournament-related it owns.

    Dispatches deletion of the live Discord scheduled event (nothing else in the
    app removes scheduled events), then removes the linked tournament, DiscordEvent
    (cascades to messages, logs, DMs) and legacy message logs, then the event row.
    Shared by EventViewSet (single delete), EventRepeaterViewSet (series delete)
    and sync_future_events' realign, so no path leaves ghost events behind.
    """

    with transaction.atomic():
        standing.on_event_deleted(event, actor=actor)
        invalidate_after_commit(event)
        if event.tournament:
            tournament = event.tournament
            event.tournament = None
            event.save(update_fields=["tournament", "updated_at"])
            tournament.delete()

        try:
            discord_event = event.discord_event
        except DiscordEvent.DoesNotExist:
            discord_event = None
        if discord_event is not None:
            if discord_event.scheduled_event_id:
                delete_discord_scheduled_event.delay(
                    discord_event.guild_id, discord_event.scheduled_event_id
                )
            discord_event.delete()

        DiscordMessageLog.objects.filter(
            source__in=["event_announcement", "event_notice"],
            source_id=event.pk,
        ).delete()

        event.delete()


def teardown_event_repeater(
    repeater: EventRepeater, *, actor: CustomUser | None = None
) -> None:
    """Delete a series after tearing down its still-active occurrences.

    Their live Discord scheduled events would otherwise come back as ghosts on the
    next sync_discord_events run. Completed and cancelled occurrences stay, with
    Event.event_repeater set to NULL, as the series' history.
    """
    active_states = [
        EventState.UPCOMING,
        EventState.SIGNUPS_OPEN,
        EventState.ROLL_CALL,
    ]
    with transaction.atomic():
        for event in list(repeater.events.filter(state__in=active_states)):
            teardown_event(event, actor=actor)
        repeater.delete()


# ---------------------------------------------------------------------------
# Lobby passwords
# ---------------------------------------------------------------------------
#
# One password per event, used by every lobby of every tournament of the
# event (lobby.passwords). A series holds the mode and, in fixed mode, the
# password; each event stores its effective password and copies it onto its
# tournament. A lobby keeps the password it was created with, so a change
# only affects lobbies created afterwards.


def is_registered_for_event(
    user: CustomUser | AnonymousUser | None, event: Event
) -> bool:
    """The user plays in the event: an accepted signup, or on a team roster.

    Accepted means APPROVED or CONFIRMED. rsvp, pending_approval,
    waitlisted, tentative, rejected and cancelled signups do not count.
    Rostered means a member or the captain of a team in the event's
    tournament.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    # nocache: a player just rejected or removed must lose access at once.
    if (
        EventSignup.objects.nocache()
        .filter(event=event, user=user, status__in=REGISTERED_SIGNUP_STATUSES)
        .exists()
    ):
        return True
    if event.tournament_id is None:
        return False
    return (
        Team.objects.nocache()
        .filter(tournament_id=event.tournament_id)
        .filter(models.Q(members=user) | models.Q(captain=user))
        .exists()
    )


def series_lobby_password(
    repeater: EventRepeater, previous_mode: str, previous_password: str
) -> str:
    """The password an on-schedule event gets from its series.

    Fixed: the series' password. Random: the event keeps its own generated
    password, and gets a new one when it had a fixed one (or none).
    """
    if repeater.dota_lobby_password_mode == PasswordMode.FIXED:
        return repeater.dota_lobby_password
    if previous_mode == PasswordMode.RANDOM and previous_password:
        return previous_password
    return generate_password()


def push_lobby_password_to_tournament(event: Event) -> bool:
    """Copy only the event's password to its tournament unless it is past.

    sync_tournament_from_event copies everything to a future tournament; this
    also reaches an in-progress one, whose next lobbies must use the new
    password. Returns whether the tournament changed.
    """
    tournament = event.tournament
    if tournament is None:
        return False
    # Decided by the database, not a possibly cached tournament.
    changed = (
        Tournament.objects.filter(pk=tournament.pk)
        .exclude(state="past")
        .exclude(dota_lobby_password=event.dota_lobby_password)
        .update(dota_lobby_password=event.dota_lobby_password)
    )
    if not changed:
        return False
    tournament.dota_lobby_password = event.dota_lobby_password
    invalidate_after_commit(tournament)
    return True


def log_lobby_password_changed(event: Event, reason: str) -> None:
    """Log that an event's lobby password changed. Never logs the value."""
    logger.info(
        "lobby_password_changed",
        system="events",
        subsystem="services",
        event_id=event.pk,
        mode=event.dota_lobby_password_mode,
        reason=reason,
    )


@transaction.atomic
def regenerate_event_lobby_password(event: Event) -> Event:
    """Give a random-mode event a new password (and its tournament)."""
    if event.dota_lobby_password_mode != PasswordMode.RANDOM:
        raise ValueError("Only a random lobby password can be regenerated.")
    event.dota_lobby_password = generate_password()
    event.save(update_fields=["dota_lobby_password", "updated_at"])
    push_lobby_password_to_tournament(event)
    invalidate_after_commit(event)
    log_lobby_password_changed(event, "regenerated")
    return event


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------

TOURNAMENT_TEMPLATE_FIELDS = [
    f.name for f in TournamentTemplateMixin._meta.get_fields() if hasattr(f, "column")
]
EVENT_CONFIG_FIELDS = [
    f.name for f in EventConfigMixin._meta.get_fields() if hasattr(f, "column")
]
DISCORD_CONFIG_FIELDS = [
    f.name for f in DiscordEventConfigMixin._meta.get_fields() if hasattr(f, "column")
]
DISCORD_TOURNAMENT_TEMPLATE_FIELDS = [
    f.name
    for f in DiscordTournamentConfigMixin._meta.get_fields()
    if hasattr(f, "column")
]
# Includes dota_lobby_password_mode but not the password itself, which
# series_lobby_password resolves.
DOTA_LOBBY_CONFIG_FIELDS = [
    f.name for f in DotaLobbyConfigMixin._meta.get_fields() if hasattr(f, "column")
]
REPEATER_CREATE_COPY_FIELDS = (
    TOURNAMENT_TEMPLATE_FIELDS
    + EVENT_CONFIG_FIELDS
    + DISCORD_CONFIG_FIELDS
    + DISCORD_TOURNAMENT_TEMPLATE_FIELDS
    + DOTA_LOBBY_CONFIG_FIELDS
)


def _python_weekday(sunday_zero_dow: int) -> int:
    """Convert Sunday=0 day-of-week to Python's datetime.weekday() (Monday=0).

    EventRepeater.day_of_week uses the JS/frontend convention (Sunday=0..Saturday=6)
    to match `DAY_LABELS` in frontend/app/components/events/schemas.ts. Python's
    `date.weekday()` returns Monday=0..Sunday=6, so we shift by one.
    """
    return (sunday_zero_dow - 1) % 7


def _get_next_occurrences(
    repeater: EventRepeater, from_date: datetime.date, to_date: datetime.date
) -> list[datetime.datetime]:
    """Calculate next occurrence datetimes for a repeater within a date range."""
    tz_info = ZoneInfo(repeater.timezone)
    occurrences = []
    end = to_date
    if repeater.ends_at:
        end = min(end, repeater.ends_at)

    if repeater.frequency == RepeatFrequency.DAILY:
        current = max(from_date, repeater.starts_at)
        while current <= end:
            dt = datetime.datetime.combine(
                current, repeater.time_of_day, tzinfo=tz_info
            )
            occurrences.append(dt)
            current += timedelta(days=1)

    elif repeater.frequency in (
        RepeatFrequency.WEEKLY,
        RepeatFrequency.EVERY_TWO_WEEKS,
    ):
        step = 7 if repeater.frequency == RepeatFrequency.WEEKLY else 14
        target_weekday = _python_weekday(repeater.day_of_week)
        current = max(from_date, repeater.starts_at)
        while current.weekday() != target_weekday:
            current += timedelta(days=1)
        while current <= end:
            dt = datetime.datetime.combine(
                current, repeater.time_of_day, tzinfo=tz_info
            )
            occurrences.append(dt)
            current += timedelta(days=step)

    elif repeater.frequency == RepeatFrequency.MONTHLY:
        target_day = repeater.starts_at.day
        current = max(from_date, repeater.starts_at)
        while current <= end:
            try:
                month_date = current.replace(day=target_day)
            except ValueError:
                last_day = calendar.monthrange(current.year, current.month)[1]
                month_date = current.replace(day=last_day)
            if from_date <= month_date <= end:
                dt = datetime.datetime.combine(
                    month_date, repeater.time_of_day, tzinfo=tz_info
                )
                occurrences.append(dt)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

    return occurrences


def _copy_mixin_fields(
    source: models.Model, target: models.Model, field_names: list[str]
) -> None:
    """Copy mixin field values from source to target model instance."""
    for field_name in field_names:
        setattr(target, field_name, getattr(source, field_name))


def _today() -> datetime.date:
    """Return today's date. Extracted for testability."""
    return datetime.date.today()


def generate_events_for_repeater(repeater: EventRepeater) -> list[Event]:
    """Generate upcoming events for a repeater. Returns list of created Events."""
    if not repeater.is_active:
        return []
    today = _today()
    if repeater.ends_at and repeater.ends_at < today:
        return []

    to_date = today + timedelta(days=repeater.generate_days_ahead)
    occurrences = _get_next_occurrences(repeater, today, to_date)

    created_events = []
    for dt in occurrences:
        if Event.objects.filter(event_repeater=repeater, scheduled_at=dt).exists():
            continue
        event = Event(
            organization=repeater.organization,
            event_repeater=repeater,
            name=repeater.name,
            description=repeater.description,
            scheduled_at=dt,
            state=EventState.UPCOMING,
            created_by=repeater.created_by,
        )
        _copy_mixin_fields(repeater, event, REPEATER_CREATE_COPY_FIELDS)
        # The series' fixed password, or a new random one.
        event.dota_lobby_password = series_lobby_password(repeater, "", "")
        event.tournament_date = dt
        apply_signup_open_policy(event, timezone.now())
        event.save()
        create_tournament_for_event(event)
        ensure_discord_event(event)
        created_events.append(event)
        if repeater.discord_notify_new_events:
            notify_new_event(event)
        if event.discord_create_event:
            notify_create_discord_event(event)
    return created_events


class OccurrenceCollision(ValueError):
    """A requested one-off timestamp collides with an existing or generated occurrence."""


def create_off_schedule_event(
    repeater: EventRepeater,
    *,
    scheduled_at: datetime.datetime,
    created_by: CustomUser | None,
    overrides: dict[str, Any] | None = None,
) -> Event:
    """Create a single event attached to `repeater` but outside its schedule.

    Mirrors generate_events_for_repeater for one caller-supplied instant. Not
    atomic, for the same reason: .delay() publishes to Redis immediately and the
    worker re-reads the row over the internal API, so an uncommitted event would
    be "not found". repeater.is_active is deliberately not checked — a paused
    series is a legitimate template.
    """
    if Event.objects.filter(
        event_repeater=repeater, scheduled_at=scheduled_at
    ).exists():
        raise OccurrenceCollision(
            "An event in this series is already scheduled for that time."
        )

    today = _today()
    horizon = max(
        scheduled_at.date(), today + timedelta(days=repeater.generate_days_ahead)
    )
    if scheduled_at in set(_get_next_occurrences(repeater, today, horizon)):
        raise OccurrenceCollision(
            "That time is a scheduled occurrence of this series. "
            "Pick a different time for a one-off event."
        )

    event = Event(
        organization=repeater.organization,
        event_repeater=repeater,
        name=repeater.name,
        description=repeater.description,
        scheduled_at=scheduled_at,
        state=EventState.UPCOMING,
        created_by=created_by,
        is_off_schedule=True,
    )
    _copy_mixin_fields(repeater, event, REPEATER_CREATE_COPY_FIELDS)
    event.dota_lobby_password = series_lobby_password(repeater, "", "")
    # Overrides win, the password included (OneOffEventCreateSerializer
    # validates it against the effective mode).
    for field_name, value in (overrides or {}).items():
        setattr(event, field_name, value)
    if event.dota_lobby_password_mode == PasswordMode.RANDOM and (
        "dota_lobby_password" not in (overrides or {})
    ):
        event.dota_lobby_password = ""  # generated by Event.save
    event.tournament_date = scheduled_at
    apply_signup_open_policy(event, timezone.now())
    event.save()

    create_tournament_for_event(event)
    ensure_discord_event(event)

    if repeater.discord_notify_new_events:
        notify_new_event(event)
    if event.discord_create_event:
        notify_create_discord_event(event)

    logger.info(
        "off_schedule_event_created",
        system="events",
        subsystem="services",
        repeater_id=repeater.pk,
        event_id=event.pk,
        scheduled_at=scheduled_at.isoformat(),
    )
    return event


@transaction.atomic
def sync_future_events(
    repeater: EventRepeater,
    *,
    realign_schedule: bool = False,
    policy_changed: bool = False,
) -> list[Event]:
    """Propagate repeater changes to all upcoming events in the series.

    Only updates events that haven't progressed past 'upcoming' state
    (i.e. signups haven't opened yet), so in-progress events are untouched.

    If realign_schedule=True (caller detected a day_of_week / time_of_day /
    timezone / starts_at / frequency / is_active change), UPCOMING rows whose
    scheduled_at is no longer in the repeater's new occurrence set are torn
    down via teardown_event (so they can't leave ghost Discord scheduled
    events behind), and any new occurrences not already present are INSERTED
    via generate_events_for_repeater. This eliminates the duplicate-occurrence
    problem where the next hourly generation produced new rows at the
    new schedule alongside the stale ones. Realign is skipped entirely for an
    inactive series — a paused series generates nothing, so realigning would
    only delete its remaining rows.

    Events with is_off_schedule=True are never realigned and never receive the
    config cascade: they are one-offs the series only hosts.

    Returns the list of touched Event instances so callers can chain a
    single invalidate_after_commit at the end of the request.

    The field cascade iterates DISCORD_CONFIG_FIELDS, which is auto-built
    from DiscordEventConfigMixin._meta.get_fields(), so every reminder
    field defined on the mixin is automatically copied. The CI guardrail
    RegistryMixinCoverageTest enforces that registry fields stay on the
    mixin.

    The signup open policy is copied only when the series policy changed
    (policy_changed), which also recomputes signups_open_at (None for manual).
    A schedule move recomputes it from each event's own policy, skipping
    manual events, so a per-event policy or hand-set time survives unrelated
    edits.
    """
    if realign_schedule and repeater.is_active:
        # Compute the new occurrence set using the same helper that
        # generate_events_for_repeater uses — guarantees timestamp equality
        # between regenerated and pre-existing rows.
        today = _today()
        to_date = today + timedelta(days=repeater.generate_days_ahead)
        new_occurrences = set(_get_next_occurrences(repeater, today, to_date))

        # Tear down UPCOMING rows that don't match the new occurrence set.
        doomed = (
            Event.objects.filter(
                event_repeater=repeater,
                state=EventState.UPCOMING,
            )
            .exclude(is_off_schedule=True)
            .exclude(scheduled_at__in=new_occurrences)
        )
        for event in list(doomed):
            teardown_event(event)

        # Generate any missing occurrences. The existing helper handles
        # the "row already exists" check via its pre-insert filter.
        generate_events_for_repeater(repeater)
    elif realign_schedule:
        logger.info(
            "realign_skipped_inactive_repeater",
            system="events",
            subsystem="services",
            repeater_id=repeater.pk,
        )

    future_events = list(
        Event.objects.filter(
            event_repeater=repeater,
            state=EventState.UPCOMING,
        )
        .exclude(is_off_schedule=True)
        .select_related("tournament")
    )
    shared_fields = ["name", "description"]
    config_fields = [
        f for f in EVENT_CONFIG_FIELDS if f not in SIGNUP_OPEN_POLICY_FIELDS
    ]
    update_fields = (
        shared_fields
        + TOURNAMENT_TEMPLATE_FIELDS
        + config_fields
        + DISCORD_CONFIG_FIELDS
        + DOTA_LOBBY_CONFIG_FIELDS
        + ["dota_lobby_password"]
    )
    if policy_changed:
        update_fields += [*SIGNUP_OPEN_POLICY_FIELDS, "signups_open_at"]
    elif realign_schedule:
        update_fields.append("signups_open_at")
    now = timezone.now()
    for event in future_events:
        previous_password = event.dota_lobby_password
        previous_mode = event.dota_lobby_password_mode
        previous_draft_options = event_draft_option_values(event)
        for field_name in shared_fields:
            setattr(event, field_name, getattr(repeater, field_name))
        _copy_mixin_fields(repeater, event, TOURNAMENT_TEMPLATE_FIELDS)
        _copy_mixin_fields(repeater, event, config_fields)
        _copy_mixin_fields(repeater, event, DISCORD_CONFIG_FIELDS)
        _copy_mixin_fields(repeater, event, DOTA_LOBBY_CONFIG_FIELDS)
        event.dota_lobby_password = series_lobby_password(
            repeater, previous_mode, previous_password
        )
        event.tournament_date = event.scheduled_at
        if policy_changed:
            _copy_mixin_fields(repeater, event, list(SIGNUP_OPEN_POLICY_FIELDS))
            apply_signup_open_policy(event, now)
        elif realign_schedule and event.signup_open_mode != SignupOpenMode.MANUAL:
            apply_signup_open_policy(event, now)
        event.save(update_fields=update_fields + ["tournament_date", "updated_at"])
        if event.dota_lobby_password != previous_password:
            log_lobby_password_changed(event, "series_cascade")
        sync_tournament_from_event(
            event, changed_draft_option_fields(previous_draft_options, event)
        )

    # Single batched invalidation post-commit
    if future_events:
        invalidate_after_commit(*future_events)

    logger.info(
        "repeater_future_events_synced",
        system="events",
        subsystem="services",
        repeater_id=repeater.pk,
        count=len(future_events),
    )
    return future_events
