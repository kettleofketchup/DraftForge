from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import Model, Prefetch
from django.utils import timezone

from app.cache_utils import invalidate_after_commit, invalidate_model, invalidate_obj
from common.game import GameType
from org.models import OrgUser, OrgUserGameMmr
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import Tournament
    from events.models import Event

log = get_logger(__name__)

DEFAULT_GAME: GameType = GameType.DOTA2
LEAGUE_GAME: GameType = GameType.DOTA2
MMR_BOUNDS: dict[int, tuple[int, int]] = {}
DEFAULT_MMR_BOUNDS: tuple[int, int] = (0, 20000)

_MEMO_ATTR = "_org_mmrs_memo"
_PREFETCH_KEY = "game_mmrs"
_DOTA_FLAG_FIELDS = ["has_active_dota_mmr", "dota_mmr_last_verified"]


class OrgMmrError(ValueError):
    pass


def resolve_game_type(value: int | None) -> GameType:
    if value in GameType.values:
        return GameType(value)
    return DEFAULT_GAME


def game_for_tournament(t: Tournament | None) -> GameType:
    return resolve_game_type(t.game_type if t is not None else None)


def game_for_event(e: Event | None) -> GameType:
    return resolve_game_type(e.game_type if e is not None else None)


def _empty_mmrs() -> dict[int, int]:
    return {game: 0 for game in GameType.values}


def _rows_for(org_user: OrgUser) -> list[OrgUserGameMmr]:
    cache = getattr(org_user, "_prefetched_objects_cache", {})
    if _PREFETCH_KEY in cache:
        return list(cache[_PREFETCH_KEY])
    log.warning(
        "org_mmr_unprefetched",
        system="org",
        subsystem="mmr",
        org_user_id=org_user.pk,
    )
    if settings.RUNNING_TESTS:
        raise AssertionError(
            f"org MMR read on OrgUser {org_user.pk} without game_mmrs prefetch"
        )
    return list(OrgUserGameMmr.objects.filter(org_user_id=org_user.pk))


def get_org_mmrs(org_user: OrgUser | None) -> dict[int, int]:
    if org_user is None:
        return _empty_mmrs()
    memo: dict[int, int] | None = getattr(org_user, _MEMO_ATTR, None)
    if memo is None:
        memo = _empty_mmrs()
        for row in _rows_for(org_user):
            memo[row.game_type] = row.mmr
        setattr(org_user, _MEMO_ATTR, memo)
    return dict(memo)


def get_org_mmr(org_user: OrgUser | None, game_type: int) -> int:
    if org_user is None:
        return 0
    memo: dict[int, int] | None = getattr(org_user, _MEMO_ATTR, None)
    if memo is not None:
        return memo.get(game_type, 0)
    for row in _rows_for(org_user):
        if row.game_type == game_type:
            return row.mmr
    return 0


def org_mmr_map(
    organization_id: int,
    user_ids: Iterable[int],
    game_type: int,
    *,
    fresh: bool = False,
) -> dict[int, int]:
    ids = list(user_ids)
    if not ids:
        return {}
    qs = OrgUserGameMmr.objects.nocache() if fresh else OrgUserGameMmr.objects.all()
    return dict(
        qs.filter(
            org_user__organization_id=organization_id,
            org_user__user_id__in=ids,
            game_type=game_type,
        ).values_list("org_user__user_id", "mmr")
    )


def org_mmr_for(organization_id: int, user_id: int, game_type: int) -> int:
    value = (
        OrgUserGameMmr.objects.filter(
            org_user__organization_id=organization_id,
            org_user__user_id=user_id,
            game_type=game_type,
        )
        .values_list("mmr", flat=True)
        .first()
    )
    return value or 0


def validate_org_mmr(game_type: int, mmr: int | None) -> None:
    if isinstance(game_type, bool) or game_type not in GameType.values:
        raise OrgMmrError(f"Unknown game_type: {game_type!r}")
    if mmr is None:
        return
    if isinstance(mmr, bool) or not isinstance(mmr, int):
        raise OrgMmrError(f"MMR must be an integer, got {mmr!r}")
    lo, hi = MMR_BOUNDS.get(game_type, DEFAULT_MMR_BOUNDS)
    if not lo <= mmr <= hi:
        raise OrgMmrError(f"MMR {mmr} is outside {lo}..{hi}")


def game_mmrs_prefetch(*, fresh: bool) -> Prefetch:
    qs = OrgUserGameMmr.objects.nocache() if fresh else OrgUserGameMmr.objects.all()
    return Prefetch(_PREFETCH_KEY, queryset=qs)


def _drop_read_caches(org_user: OrgUser) -> None:
    getattr(org_user, "_prefetched_objects_cache", {}).pop(_PREFETCH_KEY, None)
    if hasattr(org_user, _MEMO_ATTR):
        delattr(org_user, _MEMO_ATTR)


def _invalidate_each(objs: Iterable[Model]) -> None:
    for obj in objs:
        try:
            invalidate_obj(obj)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "org_mmr_invalidate_failed",
                system="org",
                subsystem="mmr",
                obj_class=obj.__class__.__name__,
                obj_pk=obj.pk,
                error=str(exc),
            )


def invalidate_org_user_tournaments(org_user: OrgUser) -> None:
    def _do() -> None:
        _invalidate_each(org_user.user.tournaments.all())

    transaction.on_commit(_do)


def mark_dota_mmr_verified(org_user: OrgUser) -> None:
    org_user.has_active_dota_mmr = True
    org_user.dota_mmr_last_verified = timezone.now()
    org_user.save(update_fields=_DOTA_FLAG_FIELDS)


def set_org_mmr(
    org_user: OrgUser,
    game_type: int,
    mmr: int | None,
    *,
    mark_verified: bool,
) -> OrgUserGameMmr | None:
    validate_org_mmr(game_type, mmr)
    value = mmr or 0
    with transaction.atomic():
        existing = (
            OrgUserGameMmr.objects.nocache()
            .filter(org_user_id=org_user.pk, game_type=game_type)
            .first()
        )
        old = existing.mmr if existing is not None else 0
        row: OrgUserGameMmr | None = None
        if value:
            if existing is None:
                row = OrgUserGameMmr.objects.create(
                    org_user=org_user, game_type=game_type, mmr=value
                )
            else:
                existing.mmr = value
                existing.save(update_fields=["mmr", "updated_at"])
                row = existing
        elif existing is not None:
            existing.delete()
        if game_type == GameType.DOTA2 and mark_verified:
            mark_dota_mmr_verified(org_user)
        _drop_read_caches(org_user)
        log.info(
            "org_mmr_set",
            system="org",
            subsystem="mmr",
            org_user_id=org_user.pk,
            game_type=game_type,
            old_mmr=old,
            new_mmr=value,
        )
        invalidate_after_commit(org_user)
        invalidate_org_user_tournaments(org_user)
    return row


def merge_org_mmrs(loser: OrgUser, keeper: OrgUser) -> None:
    with transaction.atomic():
        keeper_rows = {
            row.game_type: row
            for row in OrgUserGameMmr.objects.nocache().filter(org_user_id=keeper.pk)
        }
        moved: list[int] = []
        raised: list[int] = []
        for row in OrgUserGameMmr.objects.nocache().filter(org_user_id=loser.pk):
            target = keeper_rows.get(row.game_type)
            if target is None:
                row.org_user = keeper
                row.save(update_fields=["org_user", "updated_at"])
                keeper_rows[row.game_type] = row
                moved.append(row.game_type)
            elif target.mmr < row.mmr:
                target.mmr = row.mmr
                target.save(update_fields=["mmr", "updated_at"])
                raised.append(row.game_type)
        _drop_read_caches(keeper)
        _drop_read_caches(loser)
        log.info(
            "org_mmr_merged",
            system="org",
            subsystem="mmr",
            loser_org_user_id=loser.pk,
            keeper_org_user_id=keeper.pk,
            moved_games=moved,
            raised_games=raised,
        )
        invalidate_after_commit(loser, keeper)
        transaction.on_commit(lambda: invalidate_model(OrgUserGameMmr))
        invalidate_org_user_tournaments(keeper)


def bulk_set_org_mmrs(
    organization_id: int, game_type: int, values: dict[int, int | None]
) -> None:
    validate_org_mmr(game_type, None)
    for user_id, value in values.items():
        try:
            validate_org_mmr(game_type, value)
        except OrgMmrError as exc:
            raise OrgMmrError(f"user {user_id}: {exc}") from exc
    org_users = list(
        OrgUser.objects.nocache().filter(
            organization_id=organization_id, user_id__in=list(values)
        )
    )
    by_user = {ou.user_id: ou for ou in org_users}
    missing = sorted(set(values) - set(by_user))
    if missing:
        raise OrgMmrError(
            f"users {missing} are not members of organization {organization_id}"
        )
    upserts = [
        OrgUserGameMmr(org_user=by_user[uid], game_type=game_type, mmr=value)
        for uid, value in values.items()
        if value
    ]
    cleared = [by_user[uid].pk for uid, value in values.items() if not value]
    with transaction.atomic():
        if upserts:
            OrgUserGameMmr.objects.bulk_create(
                upserts,
                update_conflicts=True,
                unique_fields=["org_user", "game_type"],
                update_fields=["mmr", "updated_at"],
            )
        if cleared:
            OrgUserGameMmr.objects.filter(
                org_user_id__in=cleared, game_type=game_type
            ).delete()
        log.info(
            "org_mmr_set",
            system="org",
            subsystem="mmr",
            organization_id=organization_id,
            game_type=game_type,
            upserted=len(upserts),
            cleared=len(cleared),
        )
        user_ids = list(by_user)

        def _do() -> None:
            invalidate_model(OrgUserGameMmr)
            _invalidate_each(org_users)
            tournament_model: type[Tournament] = apps.get_model("app", "Tournament")
            _invalidate_each(
                tournament_model.objects.filter(users__id__in=user_ids).distinct()
            )

        transaction.on_commit(_do)
