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

import logging

from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_obj
from app.models import CustomUser

logger = logging.getLogger(__name__)

# Discord identity / profile fields copied from the duplicate onto the kept
# account when the kept account is missing them.
_CARRYOVER_FIELDS = (
    "avatar",
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

    for rel in drop._meta.related_objects:
        accessor = rel.get_accessor_name()
        manager = getattr(drop, accessor, None)
        if manager is None:
            continue
        field_name = rel.field.name

        if rel.many_to_many:
            for obj in list(manager.all()):
                related_manager = getattr(obj, field_name)
                related_manager.add(keep)
                related_manager.remove(drop)
                invalidate_obj(obj)
            continue

        # Reverse FK (one-to-many / one-to-one): repoint each row at ``keep``.
        for obj in list(manager.all()):
            setattr(obj, field_name, keep)
            try:
                with transaction.atomic():
                    obj.save(update_fields=[field_name])
            except IntegrityError:
                # ``keep`` already has an equivalent row; the duplicate is junk.
                obj.delete()

    # Carry over Discord profile fields the kept account is missing.
    changed = []
    for field in _CARRYOVER_FIELDS:
        if not getattr(keep, field, None) and getattr(drop, field, None):
            setattr(keep, field, getattr(drop, field))
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

    pairs = []
    socials = UserSocialAuth.objects.filter(provider="discord").select_related("user")
    for sa in socials:
        owner = CustomUser.objects.filter(discordId=str(sa.uid)).first()
        if owner and owner.pk != sa.user_id:
            pairs.append((owner, sa.user))
    return pairs
