from cacheops import cached_as

from user.models import BaseUserProfile, DotaUserProfile

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
        # .nocache(): the inner select_related JOIN must NOT be independently
        # cached by cacheops. cacheops only invalidates an auto-cached join
        # query on its base table (CustomUser), never on joined tables, so a
        # nickname edit (BaseUserProfile) would leave a stale base_profile in
        # the joined row. The outer @cached_as is the sole cache layer here and
        # registers the BaseUserProfile / DotaUserProfile deps correctly.
        user = (
            CustomUser.objects.select_related(
                "base_profile__dota_user_profile__positions"
            )
            .nocache()
            .filter(pk=pk)
            .first()
        )
        return TournamentUserSerializer(user).data if user else {}

    return _build()
