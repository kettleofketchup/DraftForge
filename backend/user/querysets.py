from typing import Final

from django.db.models import Model, QuerySet

PROFILE_PATHS: Final[tuple[str, ...]] = ("base_profile",)
DOTA_PROFILE_PATHS: Final[tuple[str, ...]] = (
    "base_profile",
    "base_profile__dota_user_profile__positions",
)


def with_user_profiles[M: Model](
    qs: QuerySet[M], user_path: str = "", *, dota: bool = False
) -> QuerySet[M]:
    """select_related the user profile chain and opt out of cacheops.

    cacheops does not register select_related joins as invalidation
    dependencies, so a cached queryset would serve stale profile fields.
    """
    paths = DOTA_PROFILE_PATHS if dota else PROFILE_PATHS
    if user_path:
        paths = (user_path, *(f"{user_path}__{p}" for p in paths))
    return qs.select_related(*paths).nocache()
