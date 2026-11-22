from collections import Counter
from collections.abc import Collection
from datetime import datetime

from django.db.models import Case, Count, Q, Value, When

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from org.leadership.constants import VoidKind
from org.leadership.reviews import refresh_captain_rating
from org.leadership.settings import get_leadership_settings
from org.models import ContributionPointValue, OrgLog, OrgUser
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
from org.standing import ledger
from org.standing.kinds import kinds_for
from telemetry.logging import get_logger

log = get_logger(__name__)

_through = EventCaptain.teammates.through


def _has_leadership(where: Q) -> bool:
    return (
        OrgUser.objects.nocache()
        .filter(where)
        .filter(
            Q(captained_events__isnull=False)
            | Q(captain_reviews_given__isnull=False)
            | Q(rater_pools__isnull=False)
            | Q(contribution_entries__track="leadership")
        )
        .exists()
    )


def _recompute_open(org_id: int, snapshot_ids: set[int], *, now: datetime) -> int:
    if not snapshot_ids:
        return 0
    snapshots = list(
        EventCaptain.objects.nocache()
        .select_for_update()
        .select_related("event", "captain")
        .filter(pk__in=snapshot_ids, window_closes_at__gt=now, voided_at__isnull=True)
    )
    if snapshots:
        settings = get_leadership_settings(org_id)
        for snapshot in snapshots:
            refresh_captain_rating(snapshot, settings=settings)
    return len(snapshots)


def _beats(
    kind: str, updated_at: datetime, other_kind: str, other_updated_at: datetime
) -> bool:
    moderated = kind == VoidKind.MODERATED
    if moderated != (other_kind == VoidKind.MODERATED):
        return moderated
    return updated_at > other_updated_at


def _retire_reviews(pks: Collection[int], *, now: datetime) -> set[int]:
    if not pks:
        return set()
    reviews = CaptainReview.objects.nocache().filter(pk__in=list(pks))
    anonymized = set(
        reviews.filter(
            voided_at__isnull=True,
            event_captain__voided_at__isnull=True,
            event_captain__window_closes_at__lte=now,
        ).values_list("pk", flat=True)
    )
    if anonymized:
        CaptainReview.objects.nocache().filter(pk__in=anonymized).update(rater=None)
    CaptainReview.objects.nocache().filter(pk__in=set(pks) - anonymized).delete()
    return anonymized


def _fold_reviews(target_of: dict[int, int], keep: OrgUser, *, now: datetime) -> int:
    rows = list(
        CaptainReview.objects.nocache()
        .filter(event_captain_id__in=[*target_of, *target_of.values()])
        .values_list("pk", "event_captain_id", "rater_id", "updated_at", "void_kind")
    )
    on_keep = {
        (ec_id, rater_id): (pk, updated_at, kind)
        for pk, ec_id, rater_id, updated_at, kind in rows
        if ec_id not in target_of and rater_id is not None
    }
    delete: list[int] = []
    losers: dict[int, int | None] = {}
    move: dict[int, list[int]] = {}
    for pk, ec_id, rater_id, updated_at, kind in rows:
        target = target_of.get(ec_id)
        if target is None:
            continue
        if rater_id == keep.pk:
            delete.append(pk)
            continue
        other = on_keep.get((target, rater_id))
        if other is not None:
            if not _beats(kind, updated_at, other[2], other[1]):
                losers[pk] = target
                continue
            losers[other[0]] = None
        move.setdefault(target, []).append(pk)
    if delete:
        CaptainReview.objects.nocache().filter(pk__in=delete).delete()
    for pk in _retire_reviews(losers, now=now):
        target = losers[pk]
        if target is not None:
            move.setdefault(target, []).append(pk)
    moved = [pk for pks in move.values() for pk in pks]
    if moved:
        CaptainReview.objects.nocache().filter(pk__in=moved).update(
            event_captain_id=Case(
                *(When(pk__in=pks, then=Value(target)) for target, pks in move.items())
            )
        )
    return len(moved)


def _fold_pools(target_of: dict[int, int], keep: OrgUser) -> None:
    rows = list(
        _through.objects.filter(
            eventcaptain_id__in=[*target_of, *target_of.values()]
        ).values_list("eventcaptain_id", "orguser_id")
    )
    present = {(ec_id, ou_id) for ec_id, ou_id in rows if ec_id not in target_of}
    add: list[tuple[int, int]] = []
    for ec_id, ou_id in rows:
        target = target_of.get(ec_id)
        if target is None or ou_id == keep.pk or (target, ou_id) in present:
            continue
        present.add((target, ou_id))
        add.append((target, ou_id))
    if add:
        _through.objects.bulk_create(
            _through(eventcaptain_id=ec_id, orguser_id=ou_id) for ec_id, ou_id in add
        )


def _merge_snapshots(
    drop: OrgUser, keep: OrgUser, *, now: datetime
) -> tuple[int, set[int]]:
    drop_snaps = dict(
        EventCaptain.objects.nocache()
        .filter(captain=drop)
        .values_list("pk", "event_id")
    )
    if not drop_snaps:
        return 0, set()
    keep_by_event = dict(
        EventCaptain.objects.nocache()
        .filter(captain=keep, event_id__in=set(drop_snaps.values()))
        .values_list("event_id", "pk")
    )
    target_of = {
        pk: keep_by_event[event_id]
        for pk, event_id in drop_snaps.items()
        if event_id in keep_by_event
    }
    plain = [pk for pk in drop_snaps if pk not in target_of]
    moved = 0
    if plain:
        moved += (
            EventCaptain.objects.nocache()
            .filter(pk__in=plain)
            .update(captain=keep, updated_at=now)
        )
        CaptainReview.objects.nocache().filter(
            event_captain_id__in=plain, rater=keep
        ).delete()
    if target_of:
        moved += _fold_reviews(target_of, keep, now=now)
        _fold_pools(target_of, keep)
        EventCaptain.objects.nocache().filter(pk__in=list(target_of)).delete()
    return moved, {*plain, *target_of.values()}


def _merge_reviews(
    drop: OrgUser, keep: OrgUser, *, now: datetime
) -> tuple[int, set[int]]:
    mine = list(
        CaptainReview.objects.nocache()
        .filter(rater=drop)
        .values_list(
            "pk",
            "event_captain_id",
            "updated_at",
            "void_kind",
            "event_captain__captain_id",
        )
    )
    if not mine:
        return 0, set()
    touched = {row[1] for row in mine}
    on_keep = {
        ec_id: (pk, updated_at, kind)
        for pk, ec_id, updated_at, kind in CaptainReview.objects.nocache()
        .filter(rater=keep, event_captain_id__in=touched)
        .values_list("pk", "event_captain_id", "updated_at", "void_kind")
    }
    delete: list[int] = []
    losers: list[int] = []
    move: list[int] = []
    for pk, ec_id, updated_at, kind, captain_id in mine:
        if captain_id == keep.pk:
            delete.append(pk)
            continue
        other = on_keep.get(ec_id)
        if other is not None:
            if not _beats(kind, updated_at, other[2], other[1]):
                losers.append(pk)
                continue
            losers.append(other[0])
        move.append(pk)
    if delete:
        CaptainReview.objects.nocache().filter(pk__in=delete).delete()
    _retire_reviews(losers, now=now)
    if move:
        CaptainReview.objects.nocache().filter(pk__in=move).update(rater=keep)
    return len(move), touched


def _merge_pools(drop: OrgUser, keep: OrgUser) -> int:
    has_keep = list(
        _through.objects.filter(orguser_id=keep.pk).values_list(
            "eventcaptain_id", flat=True
        )
    )
    _through.objects.filter(orguser_id=drop.pk, eventcaptain_id__in=has_keep).delete()
    moved = _through.objects.filter(orguser_id=drop.pk).update(orguser_id=keep.pk)
    _through.objects.filter(
        orguser_id=keep.pk,
        eventcaptain_id__in=EventCaptain.objects.nocache()
        .filter(captain=keep)
        .values("pk"),
    ).delete()
    return moved


def _merge_ledger(drop: OrgUser, keep: OrgUser, *, now: datetime) -> tuple[int, int]:
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
    if discard:
        rows.filter(pk__in=discard).delete()
    moved = (
        rows.filter(pk__in=move).update(org_user=keep, updated_at=now) if move else 0
    )
    return moved, len(discard)


def reassign_member(drop: OrgUser, keep: OrgUser, *, now: datetime) -> int:
    if drop.organization_id != keep.organization_id:
        raise ValueError("cannot merge leadership across organizations")
    if drop.pk == keep.pk or not _has_leadership(Q(pk=drop.pk)):
        return 0
    snapshots, touched = _merge_snapshots(drop, keep, now=now)
    reviews, rated = _merge_reviews(drop, keep, now=now)
    pools = _merge_pools(drop, keep)
    entries, discarded = _merge_ledger(drop, keep, now=now)
    recomputed = _recompute_open(keep.organization_id, touched | rated, now=now)
    moved = snapshots + reviews + pools + entries
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
    return moved


def _repoint_settings(drop: CustomUser, keep: CustomUser) -> int:
    rows = list(OrgLeadershipSettings.objects.nocache().filter(updated_by=drop))
    if not rows:
        return 0
    OrgLeadershipSettings.objects.nocache().filter(
        pk__in=[row.pk for row in rows]
    ).update(updated_by=keep)
    invalidate_after_commit(*rows)
    return len(rows)


def repoint_attribution(drop: CustomUser, keep: CustomUser) -> int:
    return (
        CaptainReview.objects.nocache().filter(voided_by=drop).update(voided_by=keep)
        + _repoint_settings(drop, keep)
        + ledger.track_rows("leadership")
        .filter(awarded_by=drop)
        .update(awarded_by=keep)
        + ContributionPointValue.objects.nocache()
        .filter(updated_by=drop, kind__in=sorted(kinds_for("leadership")))
        .update(updated_by=keep)
    )


def delete_user_rows(
    user: CustomUser, *, actor: CustomUser | None, now: datetime
) -> int:
    if not _has_leadership(Q(user=user)):
        return 0
    reviews = list(
        CaptainReview.objects.nocache()
        .filter(rater__user=user)
        .values_list("pk", "event_captain_id", "voided_at")
    )
    rated = {ec_id for _, ec_id, voided_at in reviews if voided_at is None}
    _retire_reviews([pk for pk, _, _ in reviews], now=now)
    EventCaptain.objects.nocache().filter(captain__user=user).delete()
    recomputed = 0
    for org_id, ids in _by_org(rated).items():
        recomputed += _recompute_open(org_id, ids, now=now)
    entries = ledger.track_rows("leadership").filter(org_user__user=user)
    per_org = Counter(
        {
            row["organization_id"]: row["count"]
            for row in entries.values("organization_id").annotate(count=Count("pk"))
        }
    )
    if per_org:
        entries.delete()
        OrgLog.objects.bulk_create(
            OrgLog(
                organization_id=org_id,
                actor=actor,
                action="delete_user_leadership",
                target_user=user,
                details={"user_id": user.pk, "username": user.username, "count": count},
            )
            for org_id, count in per_org.items()
        )
    deleted = sum(per_org.values())
    log.info(
        "leadership_deleted_for_user",
        system="org",
        subsystem="leadership",
        user_id=user.pk,
        actor_id=actor.pk if actor is not None else None,
        deleted=deleted,
        recomputed=recomputed,
    )
    return deleted


def _by_org(snapshot_ids: set[int]) -> dict[int, set[int]]:
    if not snapshot_ids:
        return {}
    grouped: dict[int, set[int]] = {}
    for pk, org_id in (
        EventCaptain.objects.nocache()
        .filter(pk__in=snapshot_ids)
        .values_list("pk", "organization_id")
    ):
        grouped.setdefault(org_id, set()).add(pk)
    return grouped
