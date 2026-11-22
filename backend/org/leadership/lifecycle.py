from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Prefetch

from app.models import CustomUser, Team
from draft.models.team import Draft, TeamDraftState
from events.capacity import lock_event
from events.constants import REGISTERED_SIGNUP_STATUSES
from events.models import Event, EventSignup
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.leadership.constants import VoidKind
from org.leadership.kinds import PLACEMENT_KINDS, RATED_KINDS, LeadershipKind
from org.leadership.settings import get_leadership_settings
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from org.models_leadership import CaptainReview, EventCaptain
from org.standing import ledger
from org.standing.kinds import kinds_for
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    captains: int
    awarded: int


@dataclass(frozen=True, slots=True)
class VoidResult:
    reviews_voided: int
    revoked: int


@dataclass(frozen=True, slots=True)
class _Planned:
    captain: OrgUser
    team: Team
    teammates: list[int]


def _admitted_user_ids(event: Event) -> set[int]:
    return set(
        EventSignup.objects.nocache()
        .filter(event_id=event.pk, status__in=REGISTERED_SIGNUP_STATUSES)
        .values_list("user_id", flat=True)
    )


def _attended_user_ids(event: Event) -> set[int] | None:
    if not org_has_feature(event.organization_id, FeatureKey.CONDUCT):
        return None
    return set(
        AttendanceOutcome.objects.nocache()
        .filter(event_id=event.pk, outcome=Outcome.ATTENDED, voided_at__isnull=True)
        .values_list("org_user__user_id", flat=True)
    )


def _plan(event: Event, teams: list[Team]) -> list[_Planned]:
    admitted = _admitted_user_ids(event)
    attended = _attended_user_ids(event)
    raters_ok = admitted if attended is None else admitted & attended
    wanted_users = {t.captain_id for t in teams if t.captain_id in admitted}
    for team in teams:
        wanted_users |= {m.pk for m in team.members.all()} & raters_ok
    members = {
        ou.user_id: ou
        for ou in OrgUser.objects.nocache().filter(
            organization_id=event.organization_id, user_id__in=wanted_users
        )
    }
    planned: list[_Planned] = []
    seen: set[int] = set()
    for team in teams:
        captain = members.get(team.captain_id) if team.captain_id in admitted else None
        if captain is None:
            continue
        if captain.pk in seen:
            log.warning(
                "leadership_duplicate_captain",
                system="org",
                subsystem="leadership",
                org_id=event.organization_id,
                event_id=event.pk,
                team_id=team.pk,
                org_user_id=captain.pk,
            )
            continue
        seen.add(captain.pk)
        teammates = sorted(
            members[m.pk].pk
            for m in team.members.all()
            if m.pk != team.captain_id and m.pk in raters_ok and m.pk in members
        )
        planned.append(_Planned(captain=captain, team=team, teammates=teammates))
    return planned


def _wanted_awards(
    planned: list[_Planned], points: dict[str, int], *, draft_done: bool
) -> dict[tuple[int, str], int]:
    wanted: dict[tuple[int, str], int] = {}
    for plan in planned:
        kinds = [LeadershipKind.CAPTAINED]
        placement_kind = PLACEMENT_KINDS.get(plan.team.placement or 0)
        if placement_kind is not None:
            kinds.append(placement_kind)
        if draft_done:
            kinds.append(LeadershipKind.DRAFT_COMPLETED)
        for kind in kinds:
            wanted[(plan.captain.pk, kind.value)] = points[kind.value]
    return wanted


def _write_snapshots(
    event: Event, planned: list[_Planned], *, closes: datetime
) -> None:
    existing = {
        s.captain_id: s for s in EventCaptain.objects.nocache().filter(event=event)
    }
    update: list[EventCaptain] = []
    create: list[EventCaptain] = []
    for plan in planned:
        snap = existing.get(plan.captain.pk)
        if snap is None:
            snap = EventCaptain(
                event=event,
                organization_id=event.organization_id,
                captain=plan.captain,
            )
            create.append(snap)
        else:
            update.append(snap)
        snap.team = plan.team
        snap.team_name = plan.team.name
        snap.placement = plan.team.placement
        snap.window_closes_at = closes
        snap.voided_at = None
    if update:
        EventCaptain.objects.bulk_update(
            update,
            ["team", "team_name", "placement", "window_closes_at", "voided_at"],
        )
    if create:
        EventCaptain.objects.bulk_create(create)
    snaps = {s.captain_id: s for s in [*update, *create]}
    if not snaps:
        return
    through = EventCaptain.teammates.through
    through.objects.filter(eventcaptain_id__in=[s.pk for s in snaps.values()]).delete()
    through.objects.bulk_create(
        through(eventcaptain_id=snaps[plan.captain.pk].pk, orguser_id=mate)
        for plan in planned
        for mate in plan.teammates
    )


def snapshot_event(event: Event, *, now: datetime) -> SnapshotResult:
    if (
        event.tournament_id is None
        or event.organization_id is None
        or not org_has_feature(event.organization_id, FeatureKey.LEADERSHIP)
    ):
        return SnapshotResult(captains=0, awarded=0)
    locked = lock_event(event)
    if locked.tournament_id is None:
        return SnapshotResult(captains=0, awarded=0)
    teams = list(
        Team.objects.nocache()
        .filter(tournament_id=locked.tournament_id, captain__isnull=False)
        .prefetch_related(
            Prefetch("members", queryset=CustomUser.objects.nocache().only("pk"))
        )
        .order_by("pk")
    )
    planned = _plan(locked, teams)
    draft_state = (
        Draft.objects.nocache()
        .filter(tournament_id=locked.tournament_id)
        .values_list("state", flat=True)
        .first()
    )
    settings = get_leadership_settings(locked.organization_id)
    _write_snapshots(
        locked, planned, closes=now + timedelta(hours=settings.review_window_hours)
    )
    points = ledger.points_table(locked.organization, RATED_KINDS)
    counts = ledger.sync_event_kinds(
        locked,
        kinds=RATED_KINDS,
        wanted=_wanted_awards(
            planned, points, draft_done=draft_state == TeamDraftState.COMPLETED
        ),
    )
    awarded = counts.created + counts.updated
    log.info(
        "leadership_event_snapshotted",
        system="org",
        subsystem="leadership",
        org_id=locked.organization_id,
        event_id=locked.pk,
        captains=len(planned),
        awarded=awarded,
    )
    return SnapshotResult(captains=len(planned), awarded=awarded)


def _snapshot_ids(event: Event) -> list[int]:
    return list(
        EventCaptain.objects.nocache()
        .filter(event_id=event.pk)
        .values_list("pk", flat=True)
    )


def void_event(event: Event, *, now: datetime) -> VoidResult:
    ids = _snapshot_ids(event)
    if not ids:
        return VoidResult(reviews_voided=0, revoked=0)
    EventCaptain.objects.nocache().filter(pk__in=ids, voided_at__isnull=True).update(
        voided_at=now, updated_at=now
    )
    voided = (
        CaptainReview.objects.nocache()
        .filter(event_captain_id__in=ids, voided_at__isnull=True)
        .update(voided_at=now, void_kind=VoidKind.LIFECYCLE, updated_at=now)
    )
    revoked = ledger.revoke_event_kinds(event, kinds=kinds_for("leadership"))
    log.info(
        "leadership_event_voided",
        system="org",
        subsystem="leadership",
        org_id=event.organization_id,
        event_id=event.pk,
        reviews_voided=voided,
        revoked=revoked,
    )
    return VoidResult(reviews_voided=voided, revoked=revoked)


def delete_event_rows(event: Event) -> int:
    if not _snapshot_ids(event):
        return 0
    revoked = ledger.revoke_event_kinds(event, kinds=kinds_for("leadership"))
    log.info(
        "leadership_event_rows_deleted",
        system="org",
        subsystem="leadership",
        org_id=event.organization_id,
        event_id=event.pk,
        revoked=revoked,
    )
    return revoked
