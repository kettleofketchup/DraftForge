from __future__ import annotations

from collections.abc import Callable

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from app.models import CustomUser
from league.mmr import set_league_mmr
from league.models import LeagueUser
from org.mmr import LEAGUE_GAME, OrgMmrError, validate_org_mmr
from org.mmr_official import apply_official_org_mmr
from org.mmr_requests.permissions import can_review_mmr_request, may_self_verify
from org.mmr_requests.screenshots import sanitize_screenshot
from org.mmr_requests.signals import delete_screenshots_on_commit
from org.mmr_requests.storage import private_media_storage
from org.models import MmrChangeRequest, OrgUser, OrgUserGameMmr
from org.models_mmr_requests import TEXT_MAX_LENGTH
from telemetry.logging import get_logger

log = get_logger(__name__)

MIN_REQUESTED_MMR = 1


class PendingExists(Exception):
    def __init__(self, request_id: int | None) -> None:
        super().__init__(request_id)
        self.request_id = request_id


class SelfReview(Exception):
    pass


class NotPending(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


def validate_requested_mmr(
    game_type: int, value: int, field: str = "requested_mmr"
) -> None:
    try:
        validate_org_mmr(game_type, value)
    except OrgMmrError as exc:
        raise ValidationError({field: [str(exc)]}) from exc
    if value < MIN_REQUESTED_MMR:
        raise ValidationError({field: [f"MMR must be at least {MIN_REQUESTED_MMR}"]})


def _pending_qs(
    target: str, org_user: OrgUser, league_user: LeagueUser | None, game_type: int
) -> QuerySet[MmrChangeRequest]:
    qs = MmrChangeRequest.objects.filter(
        status=MmrChangeRequest.Status.PENDING, target=target
    )
    if target == MmrChangeRequest.Target.LEAGUE:
        assert league_user is not None
        return qs.filter(league_user=league_user)
    return qs.filter(org_user=org_user, game_type=game_type)


def find_pending_request_id(
    target: str, org_user: OrgUser, league_user: LeagueUser | None, game_type: int
) -> int | None:
    return (
        _pending_qs(target, org_user, league_user, game_type)
        .values_list("pk", flat=True)
        .first()
    )


def store_with_cleanup(row: MmrChangeRequest, fn: Callable[[], None]) -> None:
    try:
        fn()
    except BaseException:
        name = row.screenshot.name
        if name:
            private_media_storage().delete(name)
        raise


def _snapshot(
    target: str, org_user: OrgUser, league_user: LeagueUser | None, game_type: int
) -> tuple[int, bool]:
    if target == MmrChangeRequest.Target.LEAGUE:
        assert league_user is not None
        return max(league_user.mmr, 0), league_user.mmr_verified_at is not None
    row = (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user_id=org_user.pk, game_type=game_type)
        .values_list("mmr", "verified_at")
        .first()
    )
    if row is None:
        return 0, False
    return row[0], row[1] is not None


def create_member_request(
    *,
    user: CustomUser,
    target: str,
    org_user: OrgUser | None,
    league_user: LeagueUser | None,
    game_type: int,
    requested_mmr: int,
    screenshot: UploadedFile,
    note: str,
) -> MmrChangeRequest:
    if target == MmrChangeRequest.Target.LEAGUE:
        if league_user is None:
            raise ValidationError({"league_user": ["This field is required."]})
        if league_user.user_id != user.pk:
            raise PermissionDenied("not_your_membership")
        org_user = league_user.org_user
        league = league_user.league
        if (
            league.organization_id is not None
            and league.organization_id != org_user.organization_id
        ):
            raise ValidationError({"league_user": ["league_org_mismatch"]})
        game_type = LEAGUE_GAME
    else:
        if org_user is None:
            raise ValidationError({"org_user": ["This field is required."]})
        if org_user.user_id != user.pk:
            raise PermissionDenied("not_your_membership")
        league = None
        league_user = None

    validate_requested_mmr(game_type, requested_mmr)

    pending_id = find_pending_request_id(target, org_user, league_user, game_type)
    if pending_id is not None:
        raise PendingExists(pending_id)

    content, content_type = sanitize_screenshot(screenshot)
    previous_mmr, previous_verified = _snapshot(
        target, org_user, league_user, game_type
    )
    row = MmrChangeRequest(
        requester=user,
        subject_user=user,
        organization_id=org_user.organization_id,
        org_user=org_user,
        league=league,
        league_user=league_user,
        target=target,
        game_type=game_type,
        requested_mmr=requested_mmr,
        previous_mmr=previous_mmr,
        previous_verified=previous_verified,
        screenshot_content_type=content_type,
        note=note,
        source=MmrChangeRequest.Source.MEMBER,
    )

    def _store() -> None:
        with transaction.atomic():
            row.screenshot.save(content.name or "upload", content, save=False)
            row.save()

    try:
        store_with_cleanup(row, _store)
    except IntegrityError as exc:
        raise PendingExists(
            _pending_qs(target, org_user, league_user, game_type)
            .values_list("pk", flat=True)
            .first()
        ) from exc

    log.info(
        "mmr_request_created",
        system="org",
        subsystem="mmr_requests",
        request_id=row.pk,
        target=target,
        organization_id=row.organization_id,
        league_id=row.league_id,
        game_type=game_type,
        requested_mmr=requested_mmr,
        previous_mmr=previous_mmr,
    )
    return row


def cancel_request(req_id: int, user: CustomUser) -> MmrChangeRequest:
    req = MmrChangeRequest.objects.get(pk=req_id)
    if req.subject_user_id != user.pk or req.source != MmrChangeRequest.Source.MEMBER:
        raise PermissionDenied("not_your_request")
    name = req.screenshot.name or ""
    with transaction.atomic():
        claimed = MmrChangeRequest.objects.filter(
            pk=req_id, status=MmrChangeRequest.Status.PENDING
        ).update(
            status=MmrChangeRequest.Status.CANCELLED,
            screenshot="",
            updated_at=timezone.now(),
        )
        if claimed == 0:
            current = (
                MmrChangeRequest.objects.filter(pk=req_id)
                .values_list("status", flat=True)
                .first()
            )
            raise NotPending(current or "")
        delete_screenshots_on_commit([name])
    log.info(
        "mmr_request_cancelled",
        system="org",
        subsystem="mmr_requests",
        request_id=req_id,
        user_id=user.pk,
    )
    return MmrChangeRequest.objects.get(pk=req_id)


def _load_for_review(req_id: int) -> MmrChangeRequest:
    return MmrChangeRequest.objects.select_related(
        "subject_user",
        "organization",
        "league",
        "league__organization",
        "org_user",
        "org_user__organization",
        "league_user",
    ).get(pk=req_id)


def _check_reviewer(reviewer: CustomUser, req: MmrChangeRequest) -> None:
    if not may_self_verify(reviewer, req.subject_user_id):
        raise SelfReview()
    if not can_review_mmr_request(reviewer, req):
        raise PermissionDenied("cannot_review")


def _current_status(req_id: int) -> str:
    return (
        MmrChangeRequest.objects.filter(pk=req_id)
        .values_list("status", flat=True)
        .first()
        or ""
    )


def _write_official(
    req: MmrChangeRequest, value: int, actor: CustomUser, source: str
) -> None:
    if req.target == MmrChangeRequest.Target.LEAGUE:
        assert req.league_user is not None
        set_league_mmr(
            req.league_user,
            value,
            actor=actor,
            verified=True,
            source=source,
            request_id=req.pk,
        )
        return
    assert req.org_user is not None
    apply_official_org_mmr(
        req.org_user,
        req.game_type,
        value,
        actor=actor,
        source=source,
        request=req,
        extra_log={"requested_mmr": req.requested_mmr},
    )


def approve_request(
    req_id: int, reviewer: CustomUser, mmr: int | None
) -> MmrChangeRequest:
    req = _load_for_review(req_id)
    _check_reviewer(reviewer, req)
    value = req.requested_mmr if mmr is None else mmr
    validate_requested_mmr(req.game_type, value, field="mmr")
    now = timezone.now()
    with transaction.atomic():
        claimed = MmrChangeRequest.objects.filter(
            pk=req_id, status=MmrChangeRequest.Status.PENDING
        ).update(
            status=MmrChangeRequest.Status.APPROVED,
            reviewed_by=reviewer,
            reviewed_at=now,
            approved_mmr=value,
            updated_at=now,
        )
        if claimed == 0:
            raise NotPending(_current_status(req_id))
        req = _load_for_review(req_id)
        _write_official(req, value, reviewer, "mmr_request")
    log.info(
        "mmr_request_approved",
        system="org",
        subsystem="mmr_requests",
        request_id=req_id,
        target=req.target,
        organization_id=req.organization_id,
        league_id=req.league_id,
        approved_mmr=value,
        adjusted=value != req.requested_mmr,
        reviewer_id=reviewer.pk,
    )
    return req


def reject_request(req_id: int, reviewer: CustomUser, reason: str) -> MmrChangeRequest:
    req = _load_for_review(req_id)
    _check_reviewer(reviewer, req)
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": ["This field is required."]})
    if len(reason) > TEXT_MAX_LENGTH:
        raise ValidationError(
            {
                "reason": [
                    f"Ensure this field has no more than {TEXT_MAX_LENGTH} characters."
                ]
            }
        )
    now = timezone.now()
    with transaction.atomic():
        claimed = MmrChangeRequest.objects.filter(
            pk=req_id, status=MmrChangeRequest.Status.PENDING
        ).update(
            status=MmrChangeRequest.Status.REJECTED,
            reviewed_by=reviewer,
            reviewed_at=now,
            rejection_reason=reason,
            updated_at=now,
        )
        if claimed == 0:
            raise NotPending(_current_status(req_id))
    log.info(
        "mmr_request_rejected",
        system="org",
        subsystem="mmr_requests",
        request_id=req_id,
        target=req.target,
        organization_id=req.organization_id,
        league_id=req.league_id,
        reviewer_id=reviewer.pk,
    )
    return MmrChangeRequest.objects.get(pk=req_id)


def staff_set_mmr(
    *,
    actor: CustomUser,
    target: str,
    org_user: OrgUser | None,
    league_user: LeagueUser | None,
    game_type: int,
    mmr: int,
    screenshot: UploadedFile | None,
    note: str,
) -> MmrChangeRequest:
    if target == MmrChangeRequest.Target.LEAGUE:
        if league_user is None:
            raise ValidationError({"league_user": ["This field is required."]})
        org_user = league_user.org_user
        league = league_user.league
        if (
            league.organization_id is not None
            and league.organization_id != org_user.organization_id
        ):
            raise ValidationError({"league_user": ["league_org_mismatch"]})
        game_type = LEAGUE_GAME
    else:
        if org_user is None:
            raise ValidationError({"org_user": ["This field is required."]})
        league = None
        league_user = None

    now = timezone.now()
    row = MmrChangeRequest(
        requester=actor,
        subject_user=org_user.user,
        organization=org_user.organization,
        org_user=org_user,
        league=league,
        league_user=league_user,
        target=target,
        game_type=game_type,
        requested_mmr=mmr,
        approved_mmr=mmr,
        note=note,
        status=MmrChangeRequest.Status.APPROVED,
        source=MmrChangeRequest.Source.STAFF,
        reviewed_by=actor,
        reviewed_at=now,
    )
    _check_reviewer(actor, row)
    validate_requested_mmr(game_type, mmr, field="mmr")

    content = None
    if screenshot is not None:
        content, row.screenshot_content_type = sanitize_screenshot(screenshot)
    row.previous_mmr, row.previous_verified = _snapshot(
        target, org_user, league_user, game_type
    )

    def _store() -> None:
        with transaction.atomic():
            if content is not None:
                row.screenshot.save(content.name or "upload", content, save=False)
            row.save()
            _write_official(row, mmr, actor, "mmr_request")

    store_with_cleanup(row, _store)
    log.info(
        "mmr_request_staff_set",
        system="org",
        subsystem="mmr_requests",
        request_id=row.pk,
        target=target,
        organization_id=row.organization_id,
        league_id=row.league_id,
        game_type=game_type,
        mmr=mmr,
        previous_mmr=row.previous_mmr,
        has_screenshot=content is not None,
        actor_id=actor.pk,
    )
    return row


def _supersede_for_merge(ids: list[int]) -> None:
    if not ids:
        return
    now = timezone.now()
    MmrChangeRequest.objects.filter(
        pk__in=ids, status=MmrChangeRequest.Status.PENDING
    ).update(
        status=MmrChangeRequest.Status.SUPERSEDED,
        reviewed_at=now,
        updated_at=now,
    )


def repoint_mmr_requests(
    claimer: CustomUser,
    target_user: CustomUser,
    org_user_pairs: list[tuple[OrgUser, OrgUser]],
    league_user_pairs: list[tuple[LeagueUser, LeagueUser]],
) -> None:
    pending = MmrChangeRequest.Status.PENDING
    superseded: list[int] = []

    for loser, keeper in org_user_pairs:
        keeper_games = set(
            MmrChangeRequest.objects.filter(
                org_user=keeper, target=MmrChangeRequest.Target.ORG, status=pending
            ).values_list("game_type", flat=True)
        )
        if keeper_games:
            superseded += list(
                MmrChangeRequest.objects.filter(
                    org_user=loser,
                    target=MmrChangeRequest.Target.ORG,
                    status=pending,
                    game_type__in=keeper_games,
                ).values_list("pk", flat=True)
            )

    for loser_lu, keeper_lu in league_user_pairs:
        if MmrChangeRequest.objects.filter(
            league_user=keeper_lu, status=pending
        ).exists():
            superseded += list(
                MmrChangeRequest.objects.filter(
                    league_user=loser_lu, status=pending
                ).values_list("pk", flat=True)
            )

    _supersede_for_merge(superseded)

    now = timezone.now()
    for loser, keeper in org_user_pairs:
        MmrChangeRequest.objects.filter(org_user=loser).update(
            org_user=keeper, updated_at=now
        )
    for loser_lu, keeper_lu in league_user_pairs:
        MmrChangeRequest.objects.filter(league_user=loser_lu).update(
            league_user=keeper_lu, updated_at=now
        )
    for field in ("subject_user", "requester", "reviewed_by"):
        MmrChangeRequest.objects.filter(**{field: target_user}).update(
            **{field: claimer}
        )

    log.info(
        "mmr_requests_repointed",
        system="org",
        subsystem="mmr_requests",
        claimer_id=claimer.pk,
        target_user_id=target_user.pk,
        org_user_pairs=[(a.pk, b.pk) for a, b in org_user_pairs],
        league_user_pairs=[(a.pk, b.pk) for a, b in league_user_pairs],
        superseded_ids=superseded,
    )
