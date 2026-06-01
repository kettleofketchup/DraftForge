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

from telemetry.logging import get_logger

from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_obj
from app.models import CustomUser

logger = get_logger(__name__)

# Discord identity / profile fields copied from the duplicate onto the kept
# account when the kept account is missing them. Split into two groups because
# after T1 (BaseUserProfile epic) `avatar` is a `@property` on CustomUser that
# proxies to base_profile.avatar — its setter persists immediately via
# `bp.save(update_fields=["avatar"])`, so it MUST NOT appear in the column-
# level `keep.save(update_fields=...)` call below (Django would raise
# ValueError: 'The following fields do not exist in this model... avatar').
_CARRYOVER_PROPERTY_FIELDS = ("avatar",)  # persisted by property setter
_CARRYOVER_COLUMN_FIELDS = (
    "discordUsername",
    "discordNickname",
    "guildNickname",
)


def merge_discord_accounts(keep: CustomUser, drop: CustomUser) -> CustomUser:
    """Fold ``drop`` into ``keep`` and delete ``drop``.

    Reassigns every reverse relation (FK and M2M) from ``drop`` to ``keep``,
    including the Discord ``social_auth`` link. On a unique conflict (``keep``
    already has the equivalent row) the duplicate row on ``drop`` is discarded.
    ``keep`` is expected to be the account that already owns ``discordId``.
    """
    if keep.pk == drop.pk:
        return keep

    from django.core.exceptions import ObjectDoesNotExist

    def _repoint(obj, field_name):
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
            # ``keep`` already has an equivalent row; the duplicate is junk.
            obj.delete()

    # Snapshot carryover values BEFORE the related-objects loop. After T1
    # the loop walks the reverse-O2O to BaseUserProfile, hits an IntegrityError
    # (keep already has one), and deletes drop.base_profile. The
    # `drop.avatar` getter reads drop.base_profile.avatar, so after that
    # delete the carryover would silently read None and the kept account
    # never inherits the avatar. Capture the values here while drop is
    # still whole.
    carryover_snapshot = {
        field: getattr(drop, field, None)
        for field in (*_CARRYOVER_PROPERTY_FIELDS, *_CARRYOVER_COLUMN_FIELDS)
    }

    # All-or-nothing: a failure mid-loop must not leave a half-merged state
    # (some relations moved, both accounts still alive). (select_for_update is
    # a no-op on this project's SQLite, so atomicity is what guards us here.)
    with transaction.atomic():
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

        changed = []
        for field in _CARRYOVER_COLUMN_FIELDS:
            value = carryover_snapshot.get(field)
            if not getattr(keep, field, None) and value:
                setattr(keep, field, value)
                changed.append(field)
        if changed:
            keep.save(update_fields=changed)

        logger.info(
            "Merged Discord account #%s (%s) into #%s (%s) discordId=%s",
            drop.pk,
            drop.username,
            keep.pk,
            keep.username,
            keep.discordId,
        )
        drop.delete()
    invalidate_obj(keep)
    return keep


def find_split_discord_accounts():
    """Find Discord IDs split across two accounts by the phantom bug.

    Returns a list of ``(keep, drop)`` pairs where:
      - ``keep`` owns ``discordId == uid`` (the phantom that holds signup data), and
      - ``drop`` owns the Discord ``social_auth`` for that ``uid`` but is a
        different row (the duplicate a failed login created).
    """
    from social_django.models import UserSocialAuth

    socials = list(
        UserSocialAuth.objects.filter(provider="discord").select_related("user")
    )
    # Single query for all candidate owners instead of one per social row (N+1).
    uids = {str(sa.uid) for sa in socials}
    owners = {
        u.discordId: u for u in CustomUser.objects.filter(discordId__in=uids)
    }

    pairs = []
    for sa in socials:
        owner = owners.get(str(sa.uid))
        if owner and owner.pk != sa.user_id:
            pairs.append((owner, sa.user))
    return pairs
