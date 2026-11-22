from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Prefetch

from app.models import CustomUser, Team, Tournament
from draft.models.team import TeamDraftState
from events.constants import REGISTERED_SIGNUP_STATUSES
from events.models import Event, EventSignup
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.leadership.constants import VoidKind
from org.leadership.kinds import (
    DEFAULT_POINTS,
    PLACEMENT_KINDS,
    RATED_KINDS,
    LeadershipKind,
)
from org.leadership.store import get_leadership_settings
from org.models import ContributionEntry, ContributionPointValue, OrgUser
from org.models_conduct import AttendanceOutcome
from org.models_leadership import CaptainReview, EventCaptain
from org.standing import ledger
from org.standing.kinds import kinds_for
from telemetry.logging import get_logger

log = get_logger(__name__)

RATED_KIND_VALUES: frozenset[str] = frozenset(k.value for k in RATED_KINDS)


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
        .filter(event_id=event.pk, outcome=Outcome.ATTENDED)
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
        if captain is None or captain.pk in seen:
            continue
        seen.add(captain.pk)
        teammates = sorted(
            members[m.pk].pk
            for m in team.members.all()
            if m.pk != team.captain_id and m.pk in raters_ok and m.pk in members
        )
        planned.append(_Planned(captain=captain, team=team, teammates=teammates))
    return planned


def _kind_points(org_id: int) -> dict[str, int]:
    overrides = dict(
        ContributionPointValue.objects.nocache()
        .filter(organization_id=org_id, kind__in=RATED_KIND_VALUES)
        .values_list("kind", "points")
    )
    return {
        kind: overrides.get(kind, points) for kind, points in DEFAULT_POINTS.items()
    }


def _award_rows(
    event: Event, planned: list[_Planned], *, draft_done: bool
) -> list[ContributionEntry]:
    points = _kind_points(event.organization_id)
    occurred_at = event.ends_at or event.scheduled_at
    rows: list[ContributionEntry] = []
    for plan in planned:
        kinds = [LeadershipKind.CAPTAINED]
        placement_kind = PLACEMENT_KINDS.get(plan.team.placement or 0)
        if placement_kind is not None:
            kinds.append(placement_kind)
        if draft_done:
            kinds.append(LeadershipKind.DRAFT_COMPLETED)
        rows.extend(
            ContributionEntry(
                org_user_id=plan.captain.pk,
                organization_id=event.organization_id,
                track="leadership",
                kind=kind.value,
                points=points[kind.value],
                event=event,
                event_name=event.name,
                occurred_at=occurred_at,
            )
            for kind in kinds
            if points[kind.value] > 0
        )
    return rows


def snapshot_event(event: Event, *, now: datetime) -> SnapshotResult:
    if event.tournament_id is None or event.organization_id is None:
        return SnapshotResult(captains=0, awarded=0)
    if not org_has_feature(event.organization_id, FeatureKey.LEADERSHIP):
        return SnapshotResult(captains=0, awarded=0)
    teams = list(
        Team.objects.nocache()
        .filter(tournament_id=event.tournament_id, captain__isnull=False)
        .prefetch_related(
            Prefetch("members", queryset=CustomUser.objects.nocache().only("pk"))
        )
        .order_by("pk")
    )
    planned = _plan(event, teams)
    draft_state = (
        Tournament.objects.nocache()
        .filter(pk=event.tournament_id)
        .values_list("draft__state", flat=True)
        .first()
    )
    settings = get_leadership_settings(event.organization_id)
    closes = now + timedelta(hours=settings.review_window_hours)

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
    through = EventCaptain.teammates.through
    if snaps:
        through.objects.filter(
            eventcaptain_id__in=[s.pk for s in snaps.values()]
        ).delete()
        through.objects.bulk_create(
            through(eventcaptain_id=snaps[plan.captain.pk].pk, orguser_id=mate)
            for plan in planned
            for mate in plan.teammates
        )

    ledger.track_rows("leadership").filter(
        event_id=event.pk, kind__in=RATED_KIND_VALUES
    ).delete()
    rows = _award_rows(
        event, planned, draft_done=draft_state == TeamDraftState.COMPLETED
    )
    ContributionEntry.objects.bulk_create(rows)
    log.info(
        "leadership_event_snapshotted",
        system="org",
        subsystem="leadership",
        org_id=event.organization_id,
        event_id=event.pk,
        captains=len(planned),
        awarded=len(rows),
    )
    return SnapshotResult(captains=len(planned), awarded=len(rows))


def void_event(event: Event, *, now: datetime) -> VoidResult:
    if not EventCaptain.objects.nocache().filter(event=event).exists():
        return VoidResult(reviews_voided=0, revoked=0)
    EventCaptain.objects.nocache().filter(event=event, voided_at__isnull=True).update(
        voided_at=now, updated_at=now
    )
    voided = (
        CaptainReview.objects.nocache()
        .filter(event_captain__event=event, voided_at__isnull=True)
        .update(voided_at=now, void_kind=VoidKind.LIFECYCLE, updated_at=now)
    )
    revoked = ledger.revoke_event_kinds(event, kinds=kinds_for("leadership"))
    if voided or revoked:
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


def delete_event(event: Event) -> int:
    return ledger.revoke_event_kinds(event, kinds=kinds_for("leadership"))
