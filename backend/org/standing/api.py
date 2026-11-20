import dataclasses
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
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
from org.standing.errors import FeatureLocked, UnknownMetric, UnknownTrack
from org.standing.periods import Period
from org.standing.serializers import track_info_data
from org.standing.types import (
    CloseSource,
    HasUserId,
    HookName,
    HookResult,
    Leaderboard,
    LogValue,
    Metric,
    OutputKeys,
    TrackInfo,
    TrackKey,
    TrackOutput,
    ViewerRoles,
)

__all__ = [
    "ViewerRoles",
    "track_info_data",
    "FeatureLocked",
    "HookResult",
    "LogValue",
    "StandingCache",
    "UnknownMetric",
    "UnknownTrack",
    "deletion_blockers",
    "leaderboard",
    "member_standing",
    "merge_users",
    "on_event_changed",
    "on_event_closed",
    "on_event_deleted",
    "on_event_reopened",
    "on_feature_toggled",
    "on_signup_withdrawn",
    "on_user_deleted",
    "promotion_order",
    "reopen_reset_fields",
    "track_metrics",
    "tracks_for",
]


def _require_atomic() -> None:
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("standing hooks must run inside the caller's atomic block")


def _checked(track: TrackBase, hook: HookName, output: TrackOutput) -> TrackOutput:
    declared = track.output_keys.get(hook, OutputKeys())
    if tuple(output.orglog) != declared.orglog or tuple(output.log) != declared.log:
        raise RuntimeError(
            f"track {track.key!r} returned undeclared output keys for {hook}"
        )
    return output


def _dispatch(hook: HookName, call: Callable[[TrackBase], TrackOutput]) -> HookResult:
    return HookResult(
        by_track={t.key: _checked(t, hook, call(t)) for t in registry.tracks()}
    )


def on_event_closed(
    event: Event,
    *,
    cancelled: bool,
    source: CloseSource,
    actor: CustomUser | None,
    now: datetime | None = None,
) -> HookResult:
    _require_atomic()
    at = now or timezone.now()
    return _dispatch(
        "on_event_closed",
        lambda t: t.on_event_closed(
            event, cancelled=cancelled, source=source, actor=actor, now=at
        ),
    )


def on_event_reopened(
    event: Event, *, actor: CustomUser | None, now: datetime | None = None
) -> HookResult:
    _require_atomic()
    at = now or timezone.now()
    return _dispatch(
        "on_event_reopened", lambda t: t.on_event_reopened(event, actor=actor, now=at)
    )


def on_event_deleted(
    event: Event, *, actor: CustomUser | None, now: datetime | None = None
) -> HookResult:
    _require_atomic()
    at = now or timezone.now()
    return _dispatch(
        "on_event_deleted", lambda t: t.on_event_deleted(event, actor=actor, now=at)
    )


def on_event_changed(
    event: Event, *, fields: frozenset[str], now: datetime | None = None
) -> HookResult:
    _require_atomic()
    at = now or timezone.now()
    return _dispatch(
        "on_event_changed", lambda t: t.on_event_changed(event, fields=fields, now=at)
    )


def on_signup_withdrawn(
    signup: EventSignup,
    *,
    prior_status: str,
    by_member: bool,
    now: datetime | None = None,
) -> HookResult:
    _require_atomic()
    at = now or timezone.now()
    return _dispatch(
        "on_signup_withdrawn",
        lambda t: t.on_signup_withdrawn(
            signup, prior_status=prior_status, by_member=by_member, now=at
        ),
    )


def on_feature_toggled(org_id: int, feature: FeatureKey, *, enabled: bool) -> None:
    _require_atomic()
    for t in registry.tracks():
        if t.feature == feature:
            t.on_feature_toggled(org_id, enabled=enabled)


def reopen_reset_fields() -> dict[str, None]:
    return {name: None for t in registry.tracks() for name in t.reopen_reset_fields}


def _fold(into: dict[str, LogValue], values: Mapping[str, LogValue]) -> None:
    for key, value in values.items():
        if key not in into:
            into[key] = value
        elif isinstance(value, bool):
            into[key] = bool(into[key]) or value
        else:
            into[key] = into[key] + value


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
    active = registry.tracks()
    orglog: dict[TrackKey, dict[str, LogValue]] = {t.key: {} for t in active}
    log: dict[TrackKey, dict[str, LogValue]] = {t.key: {} for t in active}
    for drop_ou, keep_ou in member_pairs:
        for t in active:
            out = _checked(t, "merge_members", t.merge_members(drop_ou, keep_ou))
            _fold(orglog[t.key], out.orglog)
            _fold(log[t.key], out.log)
    by_track: dict[TrackKey, TrackOutput] = {}
    for t in active:
        out = _checked(t, "repoint_user", t.repoint_user(drop, keep))
        by_track[t.key] = TrackOutput(
            orglog={**orglog[t.key], **out.orglog}, log={**log[t.key], **out.log}
        )
    return HookResult(by_track=by_track)


def on_user_deleted(user: CustomUser, *, actor: CustomUser | None) -> HookResult:
    _require_atomic()
    return _dispatch("on_user_deleted", lambda t: t.on_user_deleted(user, actor=actor))


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


def leaderboard(
    org: Organization,
    track: str,
    metric: str,
    period: Period,
    *,
    viewer: CustomUser | AnonymousUser | None,
    now: datetime | None = None,
) -> Leaderboard:
    adapter = registry.track(track)
    chosen = next((m for m in adapter.metrics if m.key == metric), None)
    if chosen is None:
        raise UnknownMetric(metric)
    if not org_has_feature(org, adapter.feature):
        raise FeatureLocked(adapter.key)
    access = adapter.access(org.pk, viewer=viewer)
    board = adapter.leaderboard(
        org,
        chosen,
        period,
        viewer=viewer,
        now=now or timezone.now(),
        access=access,
    )
    return dataclasses.replace(
        board,
        rows=board.rows if access.can_view_rows else (),
        own_row=board.own_row if access.can_view_own else None,
        rows_visible=access.can_view_rows,
    )


def tracks_for(
    org_id: int,
    *,
    viewer: CustomUser | AnonymousUser | None,
    features: Collection[str],
    roles: ViewerRoles,
) -> list[TrackInfo]:
    return [
        t.track_info(org_id, viewer=viewer, roles=roles)
        for t in registry.tracks()
        if t.feature.value in features
    ]


def member_standing(
    org_user: OrgUser,
    *,
    viewer: CustomUser | AnonymousUser | None,
    now: datetime | None = None,
) -> dict[TrackKey, Mapping[str, object]]:
    at = now or timezone.now()
    found: dict[TrackKey, Mapping[str, object]] = {}
    for t in registry.tracks():
        if not org_has_feature(org_user.organization_id, t.feature):
            continue
        block = t.member_standing(org_user, viewer=viewer, now=at)
        if block is not None:
            found[t.key] = block
    return found


def track_metrics(track: str) -> tuple[Metric, ...]:
    return registry.track(track).metrics
