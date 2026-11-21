from collections.abc import Iterable

from app.display_names import first_name, user_display_name
from app.models import CustomUser
from org.models import Organization, OrgUser


def guild_nicknames(
    org_id: int | None, user_ids: Iterable[int]
) -> dict[int, str | None]:
    ids = list(user_ids)
    if org_id is None or not ids:
        return {}
    rows = OrgUser.objects.filter(organization_id=org_id, user_id__in=ids).values_list(
        "user_id", "guild_nickname"
    )
    return {user_id: first_name(nick) for user_id, nick in rows}


def org_display_name(user: CustomUser, org_id: int | None) -> str:
    nick = guild_nicknames(org_id, [user.pk]).get(user.pk)
    return user_display_name(user, guild_nickname=nick)


def org_nicknames_public(org_id: int | None) -> bool:
    if org_id is None:
        return False
    return Organization.objects.filter(pk=org_id, members_private=False).exists()
