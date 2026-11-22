from collections.abc import Mapping
from datetime import datetime

from django.db import transaction

from app.models import CustomUser
from org.leadership.constants import (
    RATER_REVIVABLE,
    REASON_MAX_LENGTH,
    REASON_MIN_LENGTH,
    SCORE_MAX,
    SCORE_MIN,
    VoidKind,
)
from org.leadership.rating import RatingUpsert, upsert_captain_rating
from org.leadership.store import active_traits, ensure_traits
from org.models import OrgLog, OrgUser
from org.models_leadership import CaptainReview, CaptainTraitScore, EventCaptain
from telemetry.logging import get_logger

log = get_logger(__name__)


class ReviewRefused(Exception):
    def __init__(self, code: str, detail: str, *, status: int) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def _refuse(code: str, detail: str, status: int) -> ReviewRefused:
    return ReviewRefused(code, detail, status=status)


def lock_snapshot(org_id: int, event_id: int, captain_id: int) -> EventCaptain:
    snapshot = (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("captain")
        .filter(organization_id=org_id, event_id=event_id, captain_id=captain_id)
        .first()
    )
    if snapshot is None:
        raise _refuse("not_found", "No captain review for this event.", 404)
    return snapshot


def _check_writable(snapshot: EventCaptain, rater: OrgUser, *, now: datetime) -> None:
    if snapshot.voided_at is not None:
        raise _refuse("review_window_closed", "Reviews for this event are closed.", 409)
    if now >= snapshot.window_closes_at:
        raise _refuse("review_window_closed", "The review window has closed.", 409)
    if (
        snapshot.captain_id == rater.pk
        or not snapshot.teammates.filter(pk=rater.pk).exists()
    ):
        raise _refuse("not_in_pool", "You cannot review this captain.", 403)


def _existing(snapshot: EventCaptain, rater: OrgUser) -> CaptainReview | None:
    review = (
        CaptainReview.objects.nocache()
        .filter(event_captain=snapshot, rater=rater)
        .first()
    )
    if review is not None and review.void_kind == VoidKind.MODERATED:
        raise _refuse(
            "review_moderated", "This review was removed by an organizer.", 403
        )
    return review


def _validated_scores(org_id: int, scores: Mapping[str, int]) -> dict[int, int]:
    traits = active_traits(ensure_traits(org_id))
    by_key = {t.key: t for t in traits}
    missing = sorted(set(by_key) - set(scores))
    extra = sorted(set(scores) - set(by_key))
    if missing or extra:
        raise _refuse(
            "invalid_scores",
            f"Score every active trait. Missing: {missing}; unknown: {extra}.",
            400,
        )
    out: dict[int, int] = {}
    for key, value in scores.items():
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not SCORE_MIN <= value <= SCORE_MAX
        ):
            raise _refuse(
                "invalid_scores", f"{key} must be {SCORE_MIN} to {SCORE_MAX}.", 400
            )
        out[by_key[key].pk] = value
    return out


@transaction.atomic
def submit_review(
    *,
    org_id: int,
    event_id: int,
    captain_id: int,
    rater: OrgUser,
    scores: Mapping[str, int],
    now: datetime,
) -> CaptainReview:
    snapshot = lock_snapshot(org_id, event_id, captain_id)
    _check_writable(snapshot, rater, now=now)
    review = _existing(snapshot, rater)
    by_trait = _validated_scores(org_id, scores)
    if review is None:
        review = CaptainReview.objects.create(
            event_captain=snapshot, rater=rater, submitted_at=now
        )
    else:
        review.voided_at = None
        review.void_kind = ""
        review.voided_by = None
        review.void_reason = ""
        review.submitted_at = now
        review.save()
        review.scores.all().delete()
    CaptainTraitScore.objects.bulk_create(
        CaptainTraitScore(review=review, trait_id=trait_id, score=score)
        for trait_id, score in by_trait.items()
    )
    upsert_captain_rating(snapshot, now=now)
    log.info(
        "captain_review_submitted",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=event_id,
        captain_org_user_id=captain_id,
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
    *, org_id: int, event_id: int, captain_id: int, rater: OrgUser, now: datetime
) -> None:
    snapshot = lock_snapshot(org_id, event_id, captain_id)
    _check_writable(snapshot, rater, now=now)
    review = _existing(snapshot, rater)
    if review is None or review.voided_at is not None:
        raise _refuse("not_found", "You have no review to withdraw.", 404)
    review.voided_at = now
    review.void_kind = VoidKind.WITHDRAWN
    review.save(update_fields=["voided_at", "void_kind", "updated_at"])
    upsert_captain_rating(snapshot, now=now)
    log.info(
        "captain_review_withdrawn",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=event_id,
        captain_org_user_id=captain_id,
    )


def check_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not REASON_MIN_LENGTH <= len(cleaned) <= REASON_MAX_LENGTH:
        raise _refuse(
            "invalid_reason",
            f"Reason must be {REASON_MIN_LENGTH} to {REASON_MAX_LENGTH} characters.",
            400,
        )
    return cleaned


def _lock_review(org_id: int, review_pk: int) -> tuple[CaptainReview, EventCaptain]:
    snapshot_id = (
        CaptainReview.objects.nocache()
        .filter(pk=review_pk, event_captain__organization_id=org_id)
        .values_list("event_captain_id", flat=True)
        .first()
    )
    if snapshot_id is None:
        raise _refuse("not_found", "Review not found.", 404)
    snapshot = (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("captain")
        .get(pk=snapshot_id)
    )
    review = CaptainReview.objects.nocache().select_related("rater").get(pk=review_pk)
    return review, snapshot


def _check_moderator(snapshot: EventCaptain, actor: CustomUser) -> None:
    if snapshot.captain.user_id == actor.pk:
        raise _refuse(
            "cannot_moderate_own_reviews",
            "Another organizer has to moderate reviews of you.",
            403,
        )


def _moderation_log(
    action: str,
    review: CaptainReview,
    snapshot: EventCaptain,
    actor: CustomUser,
    result: RatingUpsert | None,
    reason: str,
) -> None:
    OrgLog.objects.create(
        organization_id=snapshot.organization_id,
        actor=actor,
        action=action,
        details={
            "reason": reason,
            "event_id": snapshot.event_id,
            "captain_org_user_id": snapshot.captain_id,
            "rater_org_user_id": review.rater_id,
            "points_before": result.before if result is not None else None,
            "points_after": result.after if result is not None else None,
        },
    )


@transaction.atomic
def void_review(
    *, org_id: int, review_pk: int, actor: CustomUser, reason: str, now: datetime
) -> CaptainReview:
    cleaned = check_reason(reason)
    review, snapshot = _lock_review(org_id, review_pk)
    _check_moderator(snapshot, actor)
    if review.void_kind == VoidKind.MODERATED:
        return review
    if review.voided_at is not None and review.void_kind in RATER_REVIVABLE:
        review.void_kind = VoidKind.MODERATED
    else:
        review.voided_at = now
        review.void_kind = VoidKind.MODERATED
    review.voided_by = actor
    review.void_reason = cleaned
    review.save()
    result = upsert_captain_rating(snapshot, now=now, force=True)
    _moderation_log("void_captain_review", review, snapshot, actor, result, cleaned)
    log.info(
        "captain_review_voided",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=snapshot.event_id,
        captain_org_user_id=snapshot.captain_id,
        actor_id=actor.pk,
    )
    return review


@transaction.atomic
def unvoid_review(
    *, org_id: int, review_pk: int, actor: CustomUser, reason: str, now: datetime
) -> CaptainReview:
    cleaned = check_reason(reason)
    review, snapshot = _lock_review(org_id, review_pk)
    _check_moderator(snapshot, actor)
    if review.void_kind != VoidKind.MODERATED:
        raise _refuse("not_moderated", "Only a moderated review can be restored.", 409)
    if snapshot.voided_at is not None:
        raise _refuse("review_window_closed", "Reviews for this event are closed.", 409)
    review.voided_at = None
    review.void_kind = ""
    review.voided_by = None
    review.void_reason = ""
    review.save()
    result = upsert_captain_rating(snapshot, now=now, force=True)
    _moderation_log("unvoid_captain_review", review, snapshot, actor, result, cleaned)
    log.info(
        "captain_review_unvoided",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=snapshot.event_id,
        captain_org_user_id=snapshot.captain_id,
        actor_id=actor.pk,
    )
    return review
