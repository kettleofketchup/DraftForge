from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime
from typing import Any

from django.db import connection
from django.db.models import QuerySet
from django.utils import timezone

from app.models import CustomUser, Organization
from events.models import Event, EventSignup
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import OrgUser
from org.standing import registry
from org.standing.base import TrackBase
from org.standing.cache import StandingCache
from org.standing.errors import FeatureLocked, UnknownMetric
from org.standing.periods import Period
from org.standing.types import (
    CloseSource,
    HasUserId,
    HookResult,
    Leaderboard,
    TrackInfo,
    TrackKey,
    TrackOutput,
)


def _require_atomic() -> None:
    if not connection.in_atomic_block:
        raise RuntimeError("standing hooks must run inside the caller's atomic block")


def _dispatch(call: Callable[[TrackBase], TrackOutput]) -> HookResult:
    _require_atomic()
    return HookResult(by_track={t.key: call(t) for t in registry.tracks()})


def on_event_closed(
    event: Event,
    *,
    cancelled: bool,
    source: CloseSource,
    actor: CustomUser | None,
    now: datetime | None = None,
) -> HookResult:
    at = now or timezone.now()
    return _dispatch(
        lambda t: t.on_event_closed(
            event, cancelled=cancelled, source=source, actor=actor, now=at
        )
    )


def on_event_reopened(
    event: Event, *, actor: CustomUser | None, now: datetime | None = None
) -> HookResult:
    at = now or timezone.now()
    return _dispatch(lambda t: t.on_event_reopened(event, actor=actor, now=at))


def on_event_deleted(
    event: Event, *, actor: CustomUser | None, now: datetime | None = None
) -> HookResult:
    at = now or timezone.now()
    return _dispatch(lambda t: t.on_event_deleted(event, actor=actor, now=at))


def on_event_changed(
    event: Event, *, fields: frozenset[str], now: datetime | None = None
) -> HookResult:
    at = now or timezone.now()
    return _dispatch(lambda t: t.on_event_changed(event, fields=fields, now=at))


def on_signup_withdrawn(
    signup: EventSignup,
    *,
    prior_status: str,
    by_member: bool,
    now: datetime | None = None,
) -> HookResult:
    at = now or timezone.now()
    return _dispatch(
        lambda t: t.on_signup_withdrawn(
            signup, prior_status=prior_status, by_member=by_member, now=at
        )
    )


def on_feature_toggled(org_id: int, feature: FeatureKey, *, enabled: bool) -> None:
    for t in registry.tracks():
        if t.feature == feature:
            t.on_feature_toggled(org_id, enabled=enabled)


def reopen_reset_fields() -> dict[str, None]:
    return {name: None for t in registry.tracks() for name in t.reopen_reset_fields}


def merge_users(
    drop: CustomUser,
    keep: CustomUser,
    *,
    member_pairs: Sequence[tuple[OrgUser, OrgUser]],
) -> HookResult:
    _require_atomic()
    for drop_ou, keep_ou in member_pairs:
        if drop_ou.organization_id != keep_ou.organization_id:
            raise ValueError("member pair spans two organizations")
        if drop_ou.user_id != drop.pk or keep_ou.user_id != keep.pk:
            raise ValueError("member pair does not belong to drop/keep")
    outputs: dict[str, dict[str, Any]] = {}
    for drop_ou, keep_ou in member_pairs:
        for t in registry.tracks():
            outputs.setdefault(t.key, {}).update(
                t.merge_members(drop_ou, keep_ou).orglog
            )
    for t in registry.tracks():
        outputs.setdefault(t.key, {}).update(t.repoint_user(drop, keep).orglog)
    return HookResult(
        by_track={key: TrackOutput(orglog=values) for key, values in outputs.items()}
    )


def on_user_deleted(user: CustomUser, *, actor: CustomUser | None) -> HookResult:
    return _dispatch(lambda t: t.on_user_deleted(user, actor=actor))


def deletion_blockers(user_pks: Collection[int]) -> list[QuerySet[Any]]:
    return [qs for t in registry.tracks() for qs in t.deletion_blockers(user_pks)]


def promotion_order[T: HasUserId](
    event: Event, candidates: Sequence[T], *, cache: StandingCache
) -> list[T]:
    ordered = list(candidates)
    for t in registry.tracks():
        result = t.promotion_order(event, ordered, cache=cache)
        if Counter(map(id, result)) != Counter(map(id, ordered)):
            raise ValueError(f"track {t.key!r} promotion_order is not a permutation")
        ordered = result
    return ordered


def tracks_for(
    org: Organization, *, viewer: CustomUser | None, features: Collection[str]
) -> list[TrackInfo]:
    return [
        t.track_info(org, viewer=viewer)
        for t in registry.tracks()
        if str(t.feature) in features
    ]


def leaderboard(
    org: Organization,
    track: TrackKey | str,
    metric: str,
    period: Period,
    *,
    viewer: CustomUser | None,
    now: datetime | None = None,
) -> Leaderboard:
    adapter = registry.track(track)
    chosen = next((m for m in adapter.metrics if m.key == metric), None)
    if chosen is None:
        raise UnknownMetric(metric)
    if not org_has_feature(org, adapter.feature):
        raise FeatureLocked(adapter.key)
    info = adapter.track_info(org, viewer=viewer)
    board = adapter.leaderboard(
        org, chosen, period, viewer=viewer, now=now or timezone.now()
    )
    return Leaderboard(
        track=board.track,
        metric=board.metric,
        period=board.period if chosen.periodic else "current",
        rows=board.rows if info.can_view_rows else [],
        total=board.total,
        own_row=board.own_row if info.can_view_own else None,
        rows_visible=info.can_view_rows,
    )


def member_standing(
    org_user: OrgUser,
    *,
    viewer: CustomUser | None,
    features: Collection[str],
    now: datetime | None = None,
) -> dict[str, Mapping[str, object]]:
    at = now or timezone.now()
    return {
        t.key: t.member_standing(org_user, viewer=viewer, now=at)
        for t in registry.tracks()
        if str(t.feature) in features
    }
