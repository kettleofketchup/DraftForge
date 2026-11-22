from collections import Counter
from datetime import datetime

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from app.models import CustomUser
from org.leadership.reviews import upsert_captain_rating
from org.models import OrgLog, OrgUser
from org.models_leadership import (
    CaptainReview,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)


def _recompute_open(snapshot_ids: set[int], *, now: datetime) -> int:
    if not snapshot_ids:
        return 0
    recomputed = 0
    for snapshot in (
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("captain")
        .filter(pk__in=snapshot_ids, window_closes_at__gt=now)
    ):
        if upsert_captain_rating(snapshot, now=now) is not None:
            recomputed += 1
    return recomputed


def _move_reviews(source_ids: list[int], target: EventCaptain) -> None:
    kept = {
        r.rater_id: r
        for r in CaptainReview.objects.nocache().filter(event_captain=target)
    }
    for review in CaptainReview.objects.nocache().filter(
        event_captain_id__in=source_ids
    ):
        other = kept.get(review.rater_id)
        if review.rater_id == target.captain_id:
            review.delete()
        elif other is None:
            review.event_captain = target
            review.save(update_fields=["event_captain", "updated_at"])
            kept[review.rater_id] = review
        elif review.updated_at > other.updated_at:
            other.delete()
            review.event_captain = target
            review.save(update_fields=["event_captain", "updated_at"])
            kept[review.rater_id] = review
        else:
            review.delete()


def _merge_snapshots(drop: OrgUser, keep: OrgUser) -> set[int]:
    touched: set[int] = set()
    keep_by_event = {
        s.event_id: s for s in EventCaptain.objects.nocache().filter(captain=keep)
    }
    for snap in EventCaptain.objects.nocache().filter(captain=drop):
        target = keep_by_event.get(snap.event_id)
        if target is None:
            snap.captain = keep
            snap.save(update_fields=["captain", "updated_at"])
            touched.add(snap.pk)
        else:
            _move_reviews([snap.pk], target)
            snap.delete()
            touched.add(target.pk)
    return touched


def _merge_reviews(drop: OrgUser, keep: OrgUser) -> set[int]:
    touched: set[int] = set()
    for review in (
        CaptainReview.objects.nocache()
        .filter(rater=drop)
        .select_related("event_captain")
    ):
        touched.add(review.event_captain_id)
        if review.event_captain.captain_id == keep.pk:
            review.delete()
            continue
        other = (
            CaptainReview.objects.nocache()
            .filter(event_captain_id=review.event_captain_id, rater=keep)
            .first()
        )
        if other is None:
            review.rater = keep
            review.save(update_fields=["rater", "updated_at"])
        elif review.updated_at > other.updated_at:
            other.delete()
            review.rater = keep
            review.save(update_fields=["rater", "updated_at"])
        else:
            review.delete()
    CaptainReview.objects.nocache().filter(
        rater=keep, event_captain__captain=keep
    ).delete()
    return touched


def _merge_pools(drop: OrgUser, keep: OrgUser) -> None:
    through = EventCaptain.teammates.through
    has_keep = set(
        through.objects.filter(orguser_id=keep.pk).values_list(
            "eventcaptain_id", flat=True
        )
    )
    through.objects.filter(orguser_id=drop.pk, eventcaptain_id__in=has_keep).delete()
    through.objects.filter(orguser_id=drop.pk).update(orguser_id=keep.pk)
    through.objects.filter(
        orguser_id=keep.pk,
        eventcaptain_id__in=EventCaptain.objects.filter(captain=keep).values("pk"),
    ).delete()


def _merge_ledger(drop: OrgUser, keep: OrgUser) -> tuple[int, int]:
    rows = ledger.track_rows("leadership")
    kept = set(
        rows.filter(org_user=keep, event__isnull=False).values_list("event_id", "kind")
    )
    discard: list[int] = []
    move: list[int] = []
    for pk, event_id, kind in rows.filter(org_user=drop).values_list(
        "pk", "event_id", "kind"
    ):
        (discard if (event_id, kind) in kept else move).append(pk)
    rows.filter(pk__in=discard).delete()
    moved = rows.filter(pk__in=move).update(org_user=keep, updated_at=timezone.now())
    return moved, len(discard)


def _has_leadership(members: QuerySet[OrgUser]) -> bool:
    return members.filter(
        Q(captained_events__isnull=False)
        | Q(captain_reviews_given__isnull=False)
        | Q(rater_pools__isnull=False)
        | Q(contribution_entries__track="leadership")
    ).exists()


def merge_members(drop: OrgUser, keep: OrgUser, *, now: datetime) -> None:
    if drop.organization_id != keep.organization_id:
        raise ValueError("cannot merge leadership across organizations")
    if drop.pk == keep.pk:
        return
    if not _has_leadership(OrgUser.objects.nocache().filter(pk=drop.pk)):
        return
    touched = _merge_snapshots(drop, keep)
    touched |= _merge_reviews(drop, keep)
    _merge_pools(drop, keep)
    moved, discarded = _merge_ledger(drop, keep)
    recomputed = _recompute_open(touched, now=now)
    log.info(
        "leadership_member_reassigned",
        system="org",
        subsystem="leadership",
        org_id=keep.organization_id,
        drop_org_user_id=drop.pk,
        keep_org_user_id=keep.pk,
        moved=moved,
        discarded=discarded,
        recomputed=recomputed,
    )


def repoint_user(drop: CustomUser, keep: CustomUser) -> int:
    return CaptainReview.objects.nocache().filter(voided_by=drop).update(
        voided_by=keep
    ) + OrgLeadershipSettings.objects.nocache().filter(updated_by=drop).update(
        updated_by=keep
    )


def delete_user(user: CustomUser, *, actor: CustomUser | None, now: datetime) -> int:
    if not _has_leadership(OrgUser.objects.nocache().filter(user=user)):
        return 0
    reviews = CaptainReview.objects.nocache().filter(rater__user=user)
    rated = set(
        reviews.filter(voided_at__isnull=True).values_list(
            "event_captain_id", flat=True
        )
    )
    reviews.delete()
    EventCaptain.objects.nocache().filter(captain__user=user).delete()
    _recompute_open(rated, now=now)
    entries = ledger.track_rows("leadership").filter(org_user__user=user)
    per_org = Counter(
        {
            row["organization_id"]: row["count"]
            for row in entries.values("organization_id").annotate(count=Count("pk"))
        }
    )
    if per_org:
        entries.delete()
        for org_id, count in per_org.items():
            OrgLog.objects.create(
                organization_id=org_id,
                actor=actor,
                action="delete_user_leadership",
                target_user=user,
                details={"user_id": user.pk, "username": user.username, "count": count},
            )
    deleted = sum(per_org.values())
    log.info(
        "leadership_deleted_for_user",
        system="org",
        subsystem="leadership",
        user_id=user.pk,
        actor_id=actor.pk if actor is not None else None,
        deleted=deleted,
        recomputed_snapshots=len(rated),
    )
    return deleted
