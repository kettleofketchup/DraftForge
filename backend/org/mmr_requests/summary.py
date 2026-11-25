from dataclasses import dataclass, field
from datetime import datetime

from django.contrib.auth.models import AnonymousUser
from django.db.models import BooleanField, Exists, ExpressionWrapper, F, OuterRef
from django.db.models.expressions import Window
from django.db.models.functions import RowNumber

from app.models import CustomUser, GameType
from league.models import League, LeagueUser
from org.mmr import game_mmrs_prefetch
from org.mmr_requests.schemas import (
    GameMmrEntry,
    LastDecision,
    LeagueMmrEntry,
    LeagueRef,
    OrgMmrEntry,
    OrgRef,
    PendingRequestRef,
    UserMmrSummary,
    UserRef,
)
from org.models import MmrChangeRequest, Organization, OrgUser, OrgUserGameMmr
from org.permissions import org_members_visible_q, org_staff_q

DECIDED = (
    MmrChangeRequest.Status.APPROVED,
    MmrChangeRequest.Status.REJECTED,
    MmrChangeRequest.Status.SUPERSEDED,
)

OrgKey = tuple[str, int, int]
LeagueKey = tuple[str, int]
RequestKey = OrgKey | LeagueKey


@dataclass
class _Access:
    all_access: bool = False
    visible_orgs: set[int] = field(default_factory=set)
    staff_orgs: set[int] = field(default_factory=set)
    visible_leagues: set[int] = field(default_factory=set)
    staff_leagues: set[int] = field(default_factory=set)

    def org_visible(self, org_id: int | None) -> bool:
        if org_id is None:
            return False
        return self.all_access or org_id in self.visible_orgs

    def org_reviewable(self, org_id: int) -> bool:
        return self.all_access or org_id in self.staff_orgs

    def league_visible(self, league_id: int) -> bool:
        return self.all_access or league_id in self.visible_leagues

    def league_reviewable(self, league_id: int) -> bool:
        return self.all_access or league_id in self.staff_leagues


def _resolve_access(
    viewer: CustomUser,
    org_ids: set[int],
    leagues: list[League],
) -> _Access:
    access = _Access()
    uid = viewer.pk
    if org_ids:
        rows = (
            Organization.objects.nocache()
            .filter(pk__in=org_ids)
            .annotate(
                viewer_is_staff=ExpressionWrapper(
                    org_staff_q(uid), output_field=BooleanField()
                ),
                viewer_can_view=ExpressionWrapper(
                    org_members_visible_q(uid), output_field=BooleanField()
                ),
            )
            .values_list("pk", "viewer_is_staff", "viewer_can_view")
        )
        for pk, is_staff, can_view in rows:
            if is_staff:
                access.staff_orgs.add(pk)
            if can_view:
                access.visible_orgs.add(pk)
    if leagues:
        rows = (
            League.objects.nocache()
            .filter(pk__in=[lg.pk for lg in leagues])
            .annotate(
                viewer_is_staff=ExpressionWrapper(
                    Exists(
                        League.admins.through.objects.filter(
                            league_id=OuterRef("pk"), customuser_id=uid
                        )
                    )
                    | Exists(
                        League.staff.through.objects.filter(
                            league_id=OuterRef("pk"), customuser_id=uid
                        )
                    ),
                    output_field=BooleanField(),
                ),
                viewer_is_member=Exists(
                    LeagueUser.objects.filter(league_id=OuterRef("pk"), user_id=uid)
                ),
            )
            .values_list("pk", "organization_id", "viewer_is_staff", "viewer_is_member")
        )
        for pk, org_id, is_staff, is_member in rows:
            staff = is_staff or (org_id is not None and org_id in access.staff_orgs)
            if staff:
                access.staff_leagues.add(pk)
            if org_id is not None:
                visible = org_id in access.visible_orgs
            else:
                visible = staff
            if visible or is_member:
                access.visible_leagues.add(pk)
    return access


def _user_ref(user: CustomUser | None) -> UserRef | None:
    if user is None:
        return None
    return UserRef(pk=user.pk, username=user.username)


def _org_key(org_user_id: int, game_type: int) -> OrgKey:
    return ("org", org_user_id, game_type)


def _league_key(league_user_id: int) -> LeagueKey:
    return ("league", league_user_id)


def _request_key(row: MmrChangeRequest) -> RequestKey | None:
    if row.target == MmrChangeRequest.Target.LEAGUE:
        return _league_key(row.league_user_id) if row.league_user_id else None
    return _org_key(row.org_user_id, row.game_type) if row.org_user_id else None


def _request_state(
    subject: CustomUser,
) -> tuple[dict[RequestKey, PendingRequestRef], dict[RequestKey, LastDecision]]:
    base = MmrChangeRequest.objects.filter(subject_user=subject).only(
        "pk",
        "target",
        "org_user_id",
        "league_user_id",
        "game_type",
        "status",
        "requested_mmr",
        "approved_mmr",
        "rejection_reason",
        "reviewed_at",
        "created_at",
    )
    pending: dict[RequestKey, PendingRequestRef] = {}
    for row in base.filter(status=MmrChangeRequest.Status.PENDING):
        key = _request_key(row)
        if key is not None:
            pending[key] = PendingRequestRef(
                id=row.pk,
                requested_mmr=row.requested_mmr,
                created_at=row.created_at,
            )
    latest = (
        base.filter(status__in=DECIDED)
        .annotate(
            rank=Window(
                RowNumber(),
                partition_by=[
                    F("target"),
                    F("org_user_id"),
                    F("league_user_id"),
                    F("game_type"),
                ],
                order_by=[F("reviewed_at").desc(nulls_last=True), F("pk").desc()],
            )
        )
        .filter(rank=1)
    )
    decided: dict[RequestKey, LastDecision] = {}
    for row in latest:
        key = _request_key(row)
        if key is None:
            continue
        decided[key] = LastDecision(
            id=row.pk,
            status=row.status,
            decided_mmr=(
                None
                if row.status == MmrChangeRequest.Status.REJECTED
                else row.approved_mmr
            ),
            rejection_reason=row.rejection_reason,
            reviewed_at=row.reviewed_at,
        )
    return pending, decided


def _verified_at(value: datetime | None) -> tuple[bool, datetime | None]:
    return value is not None, value


def build_user_mmr_summary(
    subject: CustomUser, viewer: CustomUser | AnonymousUser
) -> UserMmrSummary:
    empty = UserMmrSummary(user_pk=subject.pk, orgs=[], leagues=[])
    if not viewer.is_authenticated:
        return empty

    org_users: list[OrgUser] = list(
        subject.org_memberships.nocache()
        .select_related("organization")
        .prefetch_related(game_mmrs_prefetch(fresh=True))
        .order_by("organization__name", "pk")
    )
    league_users: list[LeagueUser] = list(
        subject.league_memberships.nocache()
        .select_related("league", "mmr_verified_by")
        .order_by("league__name", "pk")
    )
    if not org_users and not league_users:
        return empty

    if viewer.pk == subject.pk or viewer.is_staff or viewer.is_superuser:
        access = _Access(all_access=True)
    else:
        org_ids = {ou.organization_id for ou in org_users} | {
            lu.league.organization_id
            for lu in league_users
            if lu.league.organization_id is not None
        }
        access = _resolve_access(viewer, org_ids, [lu.league for lu in league_users])

    is_self = viewer.pk == subject.pk
    shown_orgs = [ou for ou in org_users if access.org_visible(ou.organization_id)]
    shown_leagues = [lu for lu in league_users if access.league_visible(lu.league_id)]
    org_private = {
        ou.pk: is_self or access.org_reviewable(ou.organization_id) for ou in shown_orgs
    }
    league_private = {
        lu.pk: is_self or access.league_reviewable(lu.league_id) for lu in shown_leagues
    }

    pending: dict[RequestKey, PendingRequestRef] = {}
    decided: dict[RequestKey, LastDecision] = {}
    if any(org_private.values()) or any(league_private.values()):
        pending, decided = _request_state(subject)

    orgs: list[OrgMmrEntry] = []
    for ou in shown_orgs:
        private = org_private[ou.pk]
        rows: dict[int, OrgUserGameMmr] = {
            row.game_type: row for row in ou.game_mmrs.all()
        }
        games: list[GameMmrEntry] = []
        for game in GameType:
            row = rows.get(game.value)
            verified, verified_at = _verified_at(row.verified_at if row else None)
            verified_by = row.verified_by if row else None
            key = _org_key(ou.pk, game.value)
            games.append(
                GameMmrEntry(
                    game_type=game.value,
                    mmr=row.mmr if row else 0,
                    verified=verified,
                    verified_at=verified_at,
                    verified_by=_user_ref(verified_by),
                    legacy_verified=verified and verified_by is None,
                    pending_request=pending.get(key) if private else None,
                    last_decision=decided.get(key) if private else None,
                )
            )
        org = ou.organization
        orgs.append(
            OrgMmrEntry(
                organization=OrgRef(pk=org.pk, name=org.name, logo=org.logo or None),
                org_user_pk=ou.pk if private else None,
                game_mmrs=games,
            )
        )

    leagues: list[LeagueMmrEntry] = []
    for lu in shown_leagues:
        private = league_private[lu.pk]
        verified, verified_at = _verified_at(lu.mmr_verified_at)
        key = _league_key(lu.pk)
        org_id = lu.league.organization_id
        leagues.append(
            LeagueMmrEntry(
                league=LeagueRef(pk=lu.league.pk, name=lu.league.name),
                organization_pk=org_id if access.org_visible(org_id) else None,
                league_user_pk=lu.pk if private else None,
                mmr=lu.mmr,
                verified=verified,
                verified_at=verified_at,
                verified_by=_user_ref(lu.mmr_verified_by),
                pending_request=pending.get(key) if private else None,
                last_decision=decided.get(key) if private else None,
            )
        )

    return UserMmrSummary(user_pk=subject.pk, orgs=orgs, leagues=leagues)
