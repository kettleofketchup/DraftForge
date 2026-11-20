from collections.abc import Collection, Hashable
from datetime import datetime

from org.conduct.params import ConductParams, conduct_params
from org.conduct.scoring import MemberScore, member_score, show_value
from org.models_conduct import (
    AttendanceOutcome,
    AttendanceOutcomeQuerySet,
    OrgConductSettings,
)
from org.standing.scoring import cutoff, score_groups


def _counted_rows(
    org_id: int, *, now: datetime, params: ConductParams
) -> AttendanceOutcomeQuerySet:
    return (
        AttendanceOutcome.objects.nocache()
        .counted()
        .filter(
            organization_id=org_id,
            event_starts_at__gte=cutoff(now, params.rate),
        )
    )


def _score[K: Hashable](
    rows: list[tuple[K, str, datetime]],
    *,
    now: datetime,
    params: ConductParams,
    fill: Collection[K] | None = None,
) -> dict[K, MemberScore]:
    values: list[tuple[K, float, datetime]] = []
    for key, outcome, starts_at in rows:
        value = show_value(outcome, params.late_cancel_weight)
        if value is not None:
            values.append((key, value, starts_at))
    scores = score_groups(values, now=now, params=params.rate, fill=fill)
    return {key: member_score(score) for key, score in scores.items()}


def member_scores(
    org_id: int,
    org_user_ids: Collection[int] | None,
    *,
    now: datetime,
    settings: OrgConductSettings,
) -> dict[int, MemberScore]:
    params = conduct_params(settings)
    qs = _counted_rows(org_id, now=now, params=params)
    if org_user_ids is not None:
        if not org_user_ids:
            return {}
        qs = qs.filter(org_user_id__in=org_user_ids)
    rows = list(qs.values_list("org_user_id", "outcome", "event_starts_at"))
    return _score(rows, now=now, params=params)


def user_scores(
    org_id: int,
    user_ids: Collection[int],
    *,
    now: datetime,
    settings: OrgConductSettings,
) -> dict[int, MemberScore]:
    if not user_ids:
        return {}
    params = conduct_params(settings)
    rows = list(
        _counted_rows(org_id, now=now, params=params)
        .filter(org_user__user_id__in=user_ids)
        .values_list("org_user__user_id", "outcome", "event_starts_at")
    )
    scores = _score(rows, now=now, params=params, fill=user_ids)
    return {user_id: scores[user_id] for user_id in user_ids}
