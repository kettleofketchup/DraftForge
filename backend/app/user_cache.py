from collections.abc import Iterable

from cacheops import cached_as

from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles

from .models import CustomUser
from .serializers import TournamentUserSerializer  # core fields incl. positions, no mmr


def serialize_user_core(pk: int) -> dict:
    """Per-user cached CORE serialization (no MMR — MMR is contextual).

    Invalidated only by this user's own model changes. BaseUserProfile dep is
    required: nickname/avatar are CustomUser @propertys backed by base_profile.
    DotaUserProfile dep keeps the per-user core fresh on positions/dota edits
    (positions also fire PositionsModel.save()→invalidate_obj(user); the explicit
    dep is robust + matches the test_cacheops guardrail).
    """

    @cached_as(
        CustomUser.objects.filter(pk=pk),
        BaseUserProfile.objects.filter(user_id=pk),
        DotaUserProfile.objects.filter(base_profile__user_id=pk),
        extra=f"user_core:{pk}",
        timeout=60 * 60,
    )
    def _build() -> dict:
        user = (
            with_user_profiles(CustomUser.objects.all(), dota=True)
            .filter(pk=pk)
            .first()
        )
        return TournamentUserSerializer(user).data if user else {}

    return _build()


def serialize_users_core(pks: Iterable[int]) -> dict[int, dict]:
    """Bulk CORE serialization in one uncached query; same shape as serialize_user_core."""
    users = with_user_profiles(CustomUser.objects.filter(pk__in=list(pks)), dota=True)
    return {user.pk: TournamentUserSerializer(user).data for user in users}
