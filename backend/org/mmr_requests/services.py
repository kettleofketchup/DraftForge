from __future__ import annotations

from collections.abc import Callable

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from app.models import CustomUser
from league.models import LeagueUser
from org.mmr import LEAGUE_GAME, OrgMmrError, validate_org_mmr
from org.mmr_requests.screenshots import sanitize_screenshot
from org.mmr_requests.signals import delete_screenshots_on_commit
from org.mmr_requests.storage import private_media_storage
from org.models import MmrChangeRequest, OrgUser, OrgUserGameMmr
from telemetry.logging import get_logger

log = get_logger(__name__)

MIN_REQUESTED_MMR = 1


class PendingExists(Exception):
    def __init__(self, request_id: int | None) -> None:
        super().__init__(request_id)
        self.request_id = request_id


class NotPending(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


def validate_requested_mmr(game_type: int, value: int) -> None:
    try:
        validate_org_mmr(game_type, value)
    except OrgMmrError as exc:
        raise ValidationError({"requested_mmr": [str(exc)]}) from exc
    if value < MIN_REQUESTED_MMR:
        raise ValidationError(
            {"requested_mmr": [f"MMR must be at least {MIN_REQUESTED_MMR}"]}
        )


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
