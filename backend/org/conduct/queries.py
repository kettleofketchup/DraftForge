from collections import defaultdict
from collections.abc import Collection
from datetime import datetime, timedelta

from org.conduct.scoring import (
    MemberScore,
    OutcomePoint,
    ScoreParams,
    prior_score,
    score_member,
)
from org.models_conduct import (
    AttendanceOutcome,
    AttendanceOutcomeQuerySet,
    OrgConductSettings,
)


def _counted_rows(
    org_id: int, *, now: datetime, max_age_days: int
) -> AttendanceOutcomeQuerySet:
    return (
        AttendanceOutcome.objects.nocache()
        .counted()
        .filter(
            organization_id=org_id,
            event_starts_at__gte=now - timedelta(days=max_age_days),
        )
    )


def _score_grouped(
    rows: list[tuple[int, str, datetime]], *, now: datetime, params: ScoreParams
) -> dict[int, MemberScore]:
    grouped: dict[int, list[OutcomePoint]] = defaultdict(list)
    for key, outcome, starts_at in rows:
        grouped[key].append(OutcomePoint(outcome=outcome, event_starts_at=starts_at))
    return {
        key: score_member(points, now=now, params=params)
        for key, points in grouped.items()
    }


def member_scores(
    org_id: int,
    org_user_ids: Collection[int] | None,
    *,
    now: datetime,
    settings: OrgConductSettings,
) -> dict[int, MemberScore]:
    params = ScoreParams.from_settings(settings)
    qs = _counted_rows(org_id, now=now, max_age_days=params.max_age_days)
    if org_user_ids is not None:
        if not org_user_ids:
            return {}
        qs = qs.filter(org_user_id__in=org_user_ids)
    rows = list(qs.values_list("org_user_id", "outcome", "event_starts_at"))
    return _score_grouped(rows, now=now, params=params)


def user_scores(
    org_id: int,
    user_ids: Collection[int],
    *,
    now: datetime,
    settings: OrgConductSettings,
) -> dict[int, MemberScore]:
    if not user_ids:
        return {}
    params = ScoreParams.from_settings(settings)
    rows = list(
        _counted_rows(org_id, now=now, max_age_days=params.max_age_days)
        .filter(org_user__user_id__in=user_ids)
        .values_list("org_user__user_id", "outcome", "event_starts_at")
    )
    scores = _score_grouped(rows, now=now, params=params)
    prior = prior_score(params)
    return {user_id: scores.get(user_id, prior) for user_id in user_ids}
