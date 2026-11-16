from django.db.models import Exists, OuterRef, Q

from org.models import OrgUser


def user_name_q(term: str, *, org_id: int | None = None, prefix: str = "") -> Q:
    """Match a user's username, site nickname, Discord username and global name,
    plus the server nickname in ``org_id`` when given.

    ``org_id`` must already be a validated int. ``prefix`` searches through a
    relation (e.g. ``"user__"``). SQLite folds case for ASCII only, so
    non-ASCII terms match case-sensitively.
    """
    q = (
        Q(**{f"{prefix}username__icontains": term})
        | Q(**{f"{prefix}base_profile__nickname__icontains": term})
        | Q(**{f"{prefix}discordUsername__icontains": term})
        | Q(**{f"{prefix}discordNickname__icontains": term})
    )
    if org_id is not None:
        q |= Exists(
            OrgUser.objects.filter(
                user=OuterRef(f"{prefix}pk"),
                organization_id=org_id,
                guild_nickname__icontains=term,
            )
        )
    return q
