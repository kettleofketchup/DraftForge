from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Final

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from events.models import Event
from org.leadership.constants import (
    RATER_REVIVABLE,
    REASON_MAX_LENGTH,
    SCORE_MAX,
    SCORE_MIN,
    VoidKind,
)
from org.leadership.errors import ReviewRefused
from org.leadership.kinds import LeadershipKind
from org.leadership.rating import captain_rating_points, review_mean
from org.leadership.release import annotate_live, is_released, release_floor
from org.leadership.settings import get_leadership_settings
from org.leadership.traits import materialize_traits
from org.models import ContributionEntry, Organization, OrgLog, OrgUser
from org.models_leadership import (
    CaptainReview,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.permissions import has_org_staff_access
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)


def _review_means(snapshot_id: int) -> list[Fraction]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for review_id, score in (
        CaptainTraitScore.objects.nocache()
        .filter(review__event_captain_id=snapshot_id, review__voided_at__isnull=True)
        .values_list("review_id", "score")
    ):
        grouped[review_id].append(score)
    return [review_mean(values) for values in grouped.values()]


def _current_points(ec: EventCaptain) -> int:
    return (
        ContributionEntry.objects.nocache()
        .filter(
            event_id=ec.event_id,
            org_user_id=ec.captain_id,
            kind=LeadershipKind.CAPTAIN_RATING.value,
        )
        .values_list("points", flat=True)
        .first()
        or 0
    )


def _refresh(
    ec: EventCaptain, settings: OrgLeadershipSettings
) -> tuple[int, ledger.UpsertOutcome]:
    means = _review_means(ec.pk)
    points = (
        None
        if ec.voided_at is not None
        else captain_rating_points(
            means,
            max_points=settings.rating_max_points,
            min_reviewers=settings.rating_min_reviewers,
        )
    )
    outcome = ledger.upsert_event_entry(
        event=ec.event,
        org_user=ec.captain,
        kind=LeadershipKind.CAPTAIN_RATING.value,
        points=points,
    )
    log.info(
        "captain_rating_upserted",
        system="org",
        subsystem="leadership",
        org_id=ec.organization_id,
        event_id=ec.event_id,
        captain_org_user_id=ec.captain_id,
        points=points or 0,
        reviewers=len(means),
        outcome=outcome,
    )
    return points or 0, outcome


def refresh_captain_rating(
    ec: EventCaptain, *, settings: OrgLeadershipSettings
) -> ledger.UpsertOutcome:
    return _refresh(ec, settings)[1]


def _lock_snapshot(org: Organization, event_id: int, captain_id: int) -> EventCaptain:
    ec = (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("event", "captain")
        .filter(organization=org, event_id=event_id, captain_id=captain_id)
        .first()
    )
    if ec is None:
        raise ReviewRefused("not_found", 404, "No captain review for this event.")
    return ec


def _in_pool(ec: EventCaptain, rater_id: int | None) -> bool:
    if rater_id is None or rater_id == ec.captain_id:
        return False
    return EventCaptain.teammates.through.objects.filter(
        eventcaptain_id=ec.pk, orguser_id=rater_id
    ).exists()


def _check_writable(ec: EventCaptain, rater: OrgUser, *, now: datetime) -> None:
    if ec.voided_at is not None:
        raise ReviewRefused(
            "snapshot_voided", 409, "Reviews for this event are closed."
        )
    if now >= ec.window_closes_at:
        raise ReviewRefused(
            "review_window_closed", 409, "The review window has closed."
        )
    if not _in_pool(ec, rater.pk):
        raise ReviewRefused("not_in_pool", 403, "You cannot review this captain.")


def _existing(ec: EventCaptain, rater: OrgUser) -> CaptainReview | None:
    review = (
        CaptainReview.objects.nocache().filter(event_captain=ec, rater=rater).first()
    )
    if review is not None and review.void_kind == VoidKind.MODERATED:
        raise ReviewRefused(
            "review_moderated", 403, "This review was removed by an organizer."
        )
    return review


def _validated_scores(org_id: int, scores: Mapping[str, int]) -> dict[int, int]:
    by_key = {t.key: t for t in materialize_traits(org_id) if t.active}
    missing = sorted(set(by_key) - set(scores))
    extra = sorted(set(scores) - set(by_key))
    if missing or extra:
        raise ReviewRefused(
            "invalid_scores",
            400,
            f"Score every active trait. Missing: {missing}; unknown: {extra}.",
        )
    out: dict[int, int] = {}
    for key, value in scores.items():
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not SCORE_MIN <= value <= SCORE_MAX
        ):
            raise ReviewRefused(
                "invalid_scores", 400, f"{key} must be {SCORE_MIN} to {SCORE_MAX}."
            )
        out[by_key[key].pk] = value
    return out


def _clear_void(review: CaptainReview) -> None:
    review.voided_at = None
    review.void_kind = ""
    review.voided_by = None
    review.void_reason = ""
    review.moderated_from = ""


@transaction.atomic
def submit_review(
    org: Organization,
    *,
    event_id: int,
    captain_org_user_id: int,
    rater: OrgUser,
    scores: Mapping[str, int],
    now: datetime,
) -> CaptainReview:
    ec = _lock_snapshot(org, event_id, captain_org_user_id)
    now = max(now, timezone.now())
    _check_writable(ec, rater, now=now)
    review = _existing(ec, rater)
    by_trait = _validated_scores(org.pk, scores)
    if review is None:
        review = CaptainReview.objects.create(
            event_captain=ec, rater=rater, submitted_at=now
        )
    else:
        if review.void_kind in RATER_REVIVABLE:
            _clear_void(review)
        review.submitted_at = now
        review.save()
        CaptainTraitScore.objects.nocache().filter(review=review).delete()
    CaptainTraitScore.objects.bulk_create(
        CaptainTraitScore(review=review, trait_id=trait_id, score=score)
        for trait_id, score in by_trait.items()
    )
    refresh_captain_rating(ec, settings=get_leadership_settings(org.pk))
    log.info(
        "captain_review_submitted",
        system="org",
        subsystem="leadership",
        org_id=org.pk,
        event_id=event_id,
        captain_org_user_id=captain_org_user_id,
    )
    log.debug(
        "captain_review_rater",
        system="org",
        subsystem="leadership",
        review_id=review.pk,
        rater_org_user_id=rater.pk,
    )
    return review


@transaction.atomic
def withdraw_review(
    org: Organization,
    *,
    event_id: int,
    captain_org_user_id: int,
    rater: OrgUser,
    now: datetime,
) -> None:
    ec = _lock_snapshot(org, event_id, captain_org_user_id)
    now = max(now, timezone.now())
    _check_writable(ec, rater, now=now)
    review = _existing(ec, rater)
    if review is None or review.voided_at is not None:
        raise ReviewRefused("not_found", 404, "You have no review to withdraw.")
    review.voided_at = now
    review.void_kind = VoidKind.WITHDRAWN
    review.save(update_fields=["voided_at", "void_kind", "updated_at"])
    refresh_captain_rating(ec, settings=get_leadership_settings(org.pk))
    log.info(
        "captain_review_withdrawn",
        system="org",
        subsystem="leadership",
        org_id=org.pk,
        event_id=event_id,
        captain_org_user_id=captain_org_user_id,
    )


def _check_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not 1 <= len(cleaned) <= REASON_MAX_LENGTH:
        raise ReviewRefused(
            "reason_required",
            400,
            f"A reason of 1 to {REASON_MAX_LENGTH} characters is required.",
        )
    return cleaned


def require_moderator(actor: CustomUser, org: Organization) -> None:
    if not has_org_staff_access(actor, org):
        raise ReviewRefused(
            "not_permitted", 403, "You do not have permission to moderate reviews."
        )


def _lock_review(
    org: Organization, review_id: int, actor: CustomUser
) -> tuple[CaptainReview, EventCaptain]:
    require_moderator(actor, org)
    snapshot_id = (
        CaptainReview.objects.nocache()
        .filter(pk=review_id, event_captain__organization=org)
        .exclude(event_captain__captain__user_id=actor.pk)
        .values_list("event_captain_id", flat=True)
        .first()
    )
    if snapshot_id is None:
        raise ReviewRefused("not_found", 404, "Review not found.")
    ec = (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("event", "captain")
        .get(pk=snapshot_id)
    )
    review = CaptainReview.objects.nocache().get(pk=review_id)
    return review, ec


def _moderation_log(
    action: str,
    review: CaptainReview,
    ec: EventCaptain,
    actor: CustomUser,
    *,
    before: int,
    after: int,
    reason: str | None,
) -> None:
    details: dict[str, object] = {
        "event_id": ec.event_id,
        "captain_org_user_id": ec.captain_id,
        "rater_org_user_id": review.rater_id,
        "points_before": before,
        "points_after": after,
    }
    if reason is not None:
        details["reason"] = reason
    OrgLog.objects.create(
        organization_id=ec.organization_id,
        actor=actor,
        action=action,
        details=details,
    )


@transaction.atomic
def void_review(
    org: Organization,
    *,
    review_id: int,
    actor: CustomUser,
    reason: str,
    now: datetime,
) -> CaptainReview:
    cleaned = _check_reason(reason)
    review, ec = _lock_review(org, review_id, actor)
    now = max(now, timezone.now())
    if review.void_kind == VoidKind.MODERATED:
        return review
    if review.voided_at is None:
        review.voided_at = now
    else:
        review.moderated_from = review.void_kind
    review.void_kind = VoidKind.MODERATED
    review.voided_by = actor
    review.void_reason = cleaned
    review.save()
    before = _current_points(ec)
    after, _ = _refresh(ec, get_leadership_settings(org.pk))
    _moderation_log(
        "void_captain_review",
        review,
        ec,
        actor,
        before=before,
        after=after,
        reason=cleaned,
    )
    log.info(
        "captain_review_voided",
        system="org",
        subsystem="leadership",
        org_id=org.pk,
        event_id=ec.event_id,
        captain_org_user_id=ec.captain_id,
        actor_id=actor.pk,
    )
    return review


@transaction.atomic
def unvoid_review(
    org: Organization, *, review_id: int, actor: CustomUser, now: datetime
) -> CaptainReview:
    review, ec = _lock_review(org, review_id, actor)
    if review.void_kind != VoidKind.MODERATED:
        raise ReviewRefused(
            "not_moderated", 409, "Only a moderated review can be restored."
        )
    if ec.voided_at is not None:
        raise ReviewRefused(
            "snapshot_voided", 409, "Reviews for this event are closed."
        )
    if review.moderated_from:
        review.void_kind = review.moderated_from
        review.voided_by = None
        review.void_reason = ""
        review.moderated_from = ""
    elif _in_pool(ec, review.rater_id):
        _clear_void(review)
    else:
        raise ReviewRefused(
            "not_in_pool", 409, "The rater is no longer in this captain's pool."
        )
    review.save()
    before = _current_points(ec)
    after, _ = _refresh(ec, get_leadership_settings(org.pk))
    _moderation_log(
        "unvoid_captain_review",
        review,
        ec,
        actor,
        before=before,
        after=after,
        reason=None,
    )
    log.info(
        "captain_review_unvoided",
        system="org",
        subsystem="leadership",
        org_id=org.pk,
        event_id=ec.event_id,
        captain_org_user_id=ec.captain_id,
        actor_id=actor.pk,
    )
    return review


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    released: list[int]
    skipped: list[dict[str, object]]


_RELEASE_REFUSALS: dict[str, tuple[int, str, str]] = {
    "cannot_release_own_reviews": (
        403,
        "own_snapshot",
        "Another moderator has to release results about you.",
    ),
    "snapshot_voided": (409, "voided", "Reviews for this event are closed."),
    "window_open": (409, "window_open", "The review window is still open."),
    "not_enough_reviews": (
        409,
        "not_enough_reviews",
        "Not enough reviews to release these results.",
    ),
    "already_released": (
        409,
        "already_released",
        "These results are already released.",
    ),
}
_REFUSAL_ORDER: Final[list[str]] = list(_RELEASE_REFUSALS)


def _release_refusal(
    ec: EventCaptain,
    *,
    live: int,
    actor: CustomUser,
    settings: OrgLeadershipSettings,
    now: datetime,
) -> str | None:
    if ec.captain.user_id == actor.pk:
        return "cannot_release_own_reviews"
    if ec.voided_at is not None:
        return "snapshot_voided"
    if ec.window_closes_at > now:
        return "window_open"
    if live < release_floor(settings.rating_min_reviewers):
        return "not_enough_reviews"
    if is_released(ec, live=live, settings=settings, now=now):
        return "already_released"
    return None


def _refuse(code: str) -> ReviewRefused:
    status, _, detail = _RELEASE_REFUSALS[code]
    return ReviewRefused(code, status, detail)


def _locked_snapshots(
    org: Organization, event: Event, captain_ids: list[int] | None
) -> list[EventCaptain]:
    qs = (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("captain")
        .filter(event=event, organization=org)
    )
    if captain_ids is not None:
        qs = qs.filter(captain_id__in=captain_ids)
    rows = list(qs.order_by("captain_id"))
    if captain_ids is not None and {ec.captain_id for ec in rows} != set(captain_ids):
        raise ReviewRefused("not_found", 404, "No captain review for this event.")
    return rows


def _live_counts(rows: list[EventCaptain]) -> dict[int, int]:
    return dict(
        annotate_live(
            EventCaptain.objects.nocache().filter(pk__in=[ec.pk for ec in rows])
        ).values_list("pk", "live")
    )


@transaction.atomic
def release_results(
    org: Organization,
    *,
    event: Event,
    actor: CustomUser,
    captain_ids: list[int] | None,
    now: datetime,
) -> ReleaseResult:
    require_moderator(actor, org)
    settings = get_leadership_settings(org.pk)
    if not settings.require_staff_release:
        raise ReviewRefused(
            "release_not_required",
            409,
            "Results release automatically for this org.",
        )
    rows = _locked_snapshots(org, event, captain_ids)
    live = _live_counts(rows)
    refusals = {
        ec.pk: _release_refusal(
            ec, live=live.get(ec.pk, 0), actor=actor, settings=settings, now=now
        )
        for ec in rows
    }
    if captain_ids is not None:
        codes = [code for code in refusals.values() if code is not None]
        if codes:
            raise _refuse(min(codes, key=_REFUSAL_ORDER.index))
    releasable = [ec for ec in rows if refusals[ec.pk] is None]
    if not releasable:
        raise ReviewRefused(
            "nothing_to_release", 409, "No results are waiting for release."
        )
    EventCaptain.objects.nocache().filter(
        pk__in=[ec.pk for ec in releasable], released_at__isnull=True
    ).update(released_at=now, released_by=actor)
    for ec in releasable:
        ec.released_at = now
        ec.released_by = actor
    invalidate_after_commit(*releasable)
    released = [ec.captain_id for ec in releasable]
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="release_captain_reviews",
        details={"event_id": event.pk, "captain_org_user_ids": released},
    )
    transaction.on_commit(
        lambda: log.info(
            "leadership_results_released",
            system="org",
            subsystem="leadership",
            org_id=org.pk,
            event_id=event.pk,
            actor_id=actor.pk,
            captain_org_user_ids=released,
            count=len(released),
        )
    )
    return ReleaseResult(
        released=released,
        skipped=[
            {"org_user_id": ec.captain_id, "code": _RELEASE_REFUSALS[code][1]}
            for ec in rows
            if (code := refusals[ec.pk]) is not None
        ],
    )
