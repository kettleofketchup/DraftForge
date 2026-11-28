"""Discord account reconciliation.

Background — the phantom-account bug:
A Discord *button* signup (events.discord.handlers._get_org_user) creates a
CustomUser carrying ``discordId`` for people who have never logged in. That row
holds the real EventSignup but has no social-auth link. When that person later
logs in through Discord OAuth, the pipeline used to fail to reclaim the row and
created a *second* account, then ``save_discord`` tried to write the same
``discordId`` (unique) onto it -> ``IntegrityError: UNIQUE constraint failed:
app_customuser.discordId`` -> 500, login broken.

This module reconciles the two rows: it keeps the account that already owns the
``discordId`` (and the signup history) and folds the duplicate login row into
it, moving the social-auth link and any other related data across.
"""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Model
from social_django.models import UserSocialAuth

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser
from draft.services.hero_chat import repoint_chat_attribution
from events.ledger import SignupActor
from events.merge import merge_user_signups
from events.staff import dedupe_host_helpers
from league.mmr import merge_user_league_memberships
from league.models import LeagueUser
from org.accounts import (
    delete_counts,
    lock_account_memberships,
    merge_member_dependents,
    repoint_org_attribution,
)
from org.api_connections.identity import batch_identity_changes
from org.api_connections.lifecycle import handle_credential_owner_loss
from org.integration import points as promotion_points
from org.integration.lifecycle import reconcile_promotion_identity
from org.mmr import merge_org_mmrs
from org.mmr_requests.services import repoint_mmr_requests
from org.models import OrgUser
from org.promotion.services import demote_colliding_earning_sends
from org.standing import api as standing
from telemetry.logging import get_logger
from user.models import PositionsModel

logger = get_logger(__name__)

# Fields copied from the duplicate onto the kept account when it lacks them.
# The property fields proxy to base_profile and their setters save it
# immediately, so they MUST NOT reach the column-level
# `keep.save(update_fields=...)` below (Django raises ValueError on a
# non-field name).
_CARRYOVER_PROPERTY_FIELDS = ("avatar", "nickname")
_CARRYOVER_COLUMN_FIELDS = (
    "discordUsername",
    "discordNickname",
)

_POSITION_FIELDS = ("carry", "mid", "offlane", "soft_support", "hard_support")


@dataclass(frozen=True)
class _GameProfileSnapshot:
    positions: PositionsModel | None
    has_active_dota_mmr: bool
    dota_mmr_last_verified: datetime | None
    deadlock_rank: str | None
    deadlock_rank_date: date | None


def _positions_set(positions: PositionsModel | None) -> bool:
    return positions is not None and any(
        getattr(positions, f) for f in _POSITION_FIELDS
    )


def _snapshot_game_profiles(user: CustomUser) -> _GameProfileSnapshot:
    bp = getattr(user, "base_profile", None)
    deadlock = getattr(bp, "deadlock_user_profile", None) if bp else None
    return _GameProfileSnapshot(
        positions=user.positions,
        has_active_dota_mmr=user.has_active_dota_mmr,
        dota_mmr_last_verified=user.dota_mmr_last_verified,
        deadlock_rank=deadlock.rank if deadlock else None,
        deadlock_rank_date=deadlock.rank_date if deadlock else None,
    )


def _carry_over_game_profiles(keep: CustomUser, drop: _GameProfileSnapshot) -> None:
    """Give ``keep`` the dropped account's game profile data it lacks."""
    if _positions_set(drop.positions) and not _positions_set(keep.positions):
        keep.positions = drop.positions
    if (
        drop.dota_mmr_last_verified is not None
        and keep.dota_mmr_last_verified is None
        and not keep.has_active_dota_mmr
    ):
        keep.has_active_dota_mmr = drop.has_active_dota_mmr
        keep.dota_mmr_last_verified = drop.dota_mmr_last_verified
    bp = getattr(keep, "base_profile", None)
    deadlock = getattr(bp, "deadlock_user_profile", None) if bp else None
    if drop.deadlock_rank and deadlock is not None and not deadlock.rank:
        deadlock.rank = drop.deadlock_rank
        deadlock.rank_date = drop.deadlock_rank_date
        deadlock.save(update_fields=["rank", "rank_date"])
        invalidate_after_commit(deadlock)


def merge_discord_accounts(keep: CustomUser, drop: CustomUser) -> CustomUser:
    """Fold ``drop`` into ``keep`` and delete ``drop``.

    Reassigns every reverse relation (FK and M2M) from ``drop`` to ``keep``,
    including the Discord ``social_auth`` link. Rows on a shared org
    membership (league memberships, event DMs, org game profiles) move to
    ``keep``'s membership first. Every row deleted, with the rows its delete
    cascades to, is logged as ``discord_merge_row_discarded``.

    ``keep`` wins every conflict; ``drop``'s profile data fills only fields
    ``keep`` lacks.
    ``keep`` is expected to be the account that already owns ``discordId``.
    """
    if keep.pk == drop.pk:
        return keep

    def _discard(obj: Model, field_name: str | None = None) -> None:
        pk = obj.pk
        deleted = delete_counts(obj)
        logger.info(
            "discord_merge_row_discarded",
            system="auth",
            subsystem="merge",
            model=obj._meta.label,
            pk=pk,
            field=field_name,
            deleted=deleted,
            kept_user_id=keep.pk,
            dropped_user_id=drop.pk,
        )

    def _repoint(obj: Model, field_name: str) -> None:
        """Move one related row to ``keep``; drop it if ``keep`` already has it.

        IMPORTANT: ``setattr(obj, field_name, keep)`` triggers Django's
        bidirectional O2O descriptor — it ALSO sets ``keep.<reverse_accessor> =
        obj`` in keep's in-memory cache. If the save() below raises IntegrityError
        and we call ``obj.delete()`` to discard the duplicate, the deleted (pk=None)
        ``obj`` is STILL cached on ``keep`` via that reverse accessor. Any
        subsequent ``keep.<field>`` access that proxies through that reverse-O2O
        (e.g. ``keep.avatar`` proxying through ``keep.base_profile.avatar``) reads
        from a dead reference and writes to a pk-less row, raising
        ``ValueError: Cannot force an update in save() with no primary key.``
        The merge loop calls ``keep.refresh_from_db()`` AFTER all repoints to
        purge those stale caches.
        """
        setattr(obj, field_name, keep)
        try:
            with transaction.atomic():
                obj.save(update_fields=[field_name])
        except IntegrityError:
            _discard(obj, field_name)

    # Snapshot carryover values BEFORE the related-objects loop. The loop
    # walks the reverse-O2O to BaseUserProfile, hits an IntegrityError
    # (keep already has one), and deletes drop.base_profile. The
    # `drop.avatar` getter reads drop.base_profile.avatar, so after that
    # delete the carryover would silently read None and the kept account
    # never inherits the avatar. Capture the values here while drop is
    # still whole.
    carryover_snapshot = {
        field: getattr(drop, field, None)
        for field in (*_CARRYOVER_PROPERTY_FIELDS, *_CARRYOVER_COLUMN_FIELDS)
    }
    game_snapshot = _snapshot_game_profiles(drop)
    dropped_steam_account_id = drop.steam_account_id
    # Both Discord IDs, before the merge rewrites either account, for the
    # promotion points settled once the sends have moved.
    merged_discord_ids = {keep.discordId or "", drop.discordId or ""}

    # All-or-nothing: a failure mid-loop must not leave a half-merged state
    # (some relations moved, both accounts still alive). (select_for_update is
    # a no-op on this project's SQLite, so atomicity is what guards us here.)
    with transaction.atomic(), batch_identity_changes():
        lock_account_memberships([drop, keep])
        handle_credential_owner_loss(drop)
        keep_org_users = {
            ou.organization_id: ou for ou in OrgUser.objects.filter(user=keep)
        }
        pairs: list[tuple[OrgUser, OrgUser]] = []
        for drop_ou in OrgUser.objects.filter(user=drop):
            keep_ou = keep_org_users.get(drop_ou.organization_id)
            if keep_ou is not None:
                if not keep_ou.guild_nickname and drop_ou.guild_nickname:
                    keep_ou.guild_nickname = drop_ou.guild_nickname
                    keep_ou.save(update_fields=["guild_nickname"])
                    invalidate_after_commit(keep)
                merge_org_mmrs(drop_ou, keep_ou)
                pairs.append((drop_ou, keep_ou))
        standing.merge_users(drop, keep, member_pairs=pairs)
        repoint_org_attribution(drop, keep)
        repoint_chat_attribution(drop, keep)
        league_pairs = merge_user_league_memberships(drop, keep, pairs)
        repoint_mmr_requests(keep, drop, pairs, league_pairs)
        for drop_ou, keep_ou in pairs:
            merge_member_dependents(drop_ou, keep_ou, discard=_discard)
            _discard(drop_ou)
        LeagueUser.objects.filter(pk__in=[lu.pk for lu, _ in league_pairs]).delete()
        demote_colliding_earning_sends(keep, drop)
        reconcile_promotion_identity(keep, drop)
        merge_user_signups(
            drop,
            keep,
            actor=SignupActor.system(correlation_id=f"merge-{uuid4().hex[:12]}"),
        )

        for rel in drop._meta.related_objects:
            accessor = rel.get_accessor_name()
            field_name = rel.field.name

            if rel.one_to_one:
                # Reverse O2O accessor yields a single object (or raises if
                # absent), not a manager — handle it on its own.
                try:
                    obj = getattr(drop, accessor)
                except ObjectDoesNotExist:
                    continue
                if obj is not None:
                    _repoint(obj, field_name)
                continue

            manager = getattr(drop, accessor, None)
            if manager is None:
                continue

            if rel.many_to_many:
                for obj in list(manager.all()):
                    related_manager = getattr(obj, field_name)
                    related_manager.add(keep)
                    related_manager.remove(drop)
                    invalidate_obj(obj)
                continue

            # Reverse FK (one-to-many): repoint each row at ``keep``.
            for obj in list(manager.all()):
                _repoint(obj, field_name)

        dedupe_host_helpers(keep)
        promotion_points.settle_after_merge(keep, merged_discord_ids)

        # Purge keep's reverse-relation caches before reading/writing through
        # them in the carryover loop. The related-objects loop above poisoned
        # some of those caches with deleted (pk=None) references via the
        # bidirectional O2O descriptor — see _repoint docstring.
        keep.refresh_from_db()

        # Carry over Discord profile fields the kept account is missing.
        # Read from carryover_snapshot (captured pre-loop) rather than
        # drop.<field>, because the related-objects loop above destroyed
        # drop.base_profile via IntegrityError → delete, so a fresh read
        # of drop.avatar would return None.
        # Property fields persist via their setters (no CustomUser.save needed);
        # column fields collect into `changed` for one batched save.
        for field in _CARRYOVER_PROPERTY_FIELDS:
            value = carryover_snapshot.get(field)
            if not getattr(keep, field, None) and value:
                setattr(keep, field, value)

        _carry_over_game_profiles(keep, game_snapshot)

        changed = []
        for field in _CARRYOVER_COLUMN_FIELDS:
            value = carryover_snapshot.get(field)
            if not getattr(keep, field, None) and value:
                setattr(keep, field, value)
                changed.append(field)
        if keep.steam_account_id is None and dropped_steam_account_id is not None:
            # steam_account_id is unique: free it on drop before keep takes it.
            CustomUser.objects.filter(pk=drop.pk).update(
                steam_account_id=None, steamid=None
            )
            keep.steam_account_id = dropped_steam_account_id
            changed.extend(["steam_account_id", "steamid"])
        if changed:
            keep.save(update_fields=changed)

        logger.info(
            "discord_accounts_merged",
            system="auth",
            subsystem="merge",
            dropped_user_id=drop.pk,
            dropped_username=drop.username,
            kept_user_id=keep.pk,
            kept_username=keep.username,
            discord_id=keep.discordId,
            dropped_steam_account_id=dropped_steam_account_id,
        )
        drop.delete()
    invalidate_obj(keep)
    return keep


def find_split_discord_accounts() -> list[tuple[CustomUser, CustomUser]]:
    """Find Discord IDs split across two accounts by the phantom bug.

    Returns a list of ``(keep, drop)`` pairs where:
      - ``keep`` owns ``discordId == uid`` (the phantom that holds signup data), and
      - ``drop`` owns the Discord ``social_auth`` for that ``uid`` but is a
        different row (the duplicate a failed login created).
    """
    socials = list(
        UserSocialAuth.objects.filter(provider="discord").select_related("user")
    )
    # Single query for all candidate owners instead of one per social row (N+1).
    uids = {str(sa.uid) for sa in socials}
    owners = {u.discordId: u for u in CustomUser.objects.filter(discordId__in=uids)}

    pairs = []
    for sa in socials:
        owner = owners.get(str(sa.uid))
        if owner and owner.pk != sa.user_id:
            pairs.append((owner, sa.user))
    return pairs
