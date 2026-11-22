from django.db.models import Q

from app.models import CustomUser
from league.models import League
from league.permissions import has_league_admin_access, has_league_staff_access
from org.models import MmrChangeRequest, Organization
from org.permissions import has_org_admin_access, has_org_staff_access


def may_self_verify(actor: CustomUser | None, subject_user_id: int) -> bool:
    if actor is None or actor.is_superuser:
        return True
    return actor.pk != subject_user_id


def can_review_target(
    user: CustomUser,
    *,
    organization: Organization | None,
    league: League | None,
    target: str,
) -> bool:
    if target == MmrChangeRequest.Target.LEAGUE:
        return league is not None and has_league_staff_access(user, league)
    return organization is not None and has_org_staff_access(user, organization)


def can_review_mmr_request(user: CustomUser, req: MmrChangeRequest) -> bool:
    if not user.is_authenticated:
        return False
    if not may_self_verify(user, req.subject_user_id):
        return False
    is_league = req.target == MmrChangeRequest.Target.LEAGUE
    if not can_review_target(
        user, organization=req.organization, league=req.league, target=req.target
    ):
        return False
    if user.is_superuser:
        return True
    subject = req.subject_user
    if is_league:
        assert req.league is not None
        if has_league_staff_access(subject, req.league):
            return has_league_admin_access(user, req.league)
        return True
    if has_org_staff_access(subject, req.organization):
        return has_org_admin_access(user, req.organization)
    return True


def org_queue_filter(org_id: int) -> Q:
    return Q(organization_id=org_id) & (
        Q(target=MmrChangeRequest.Target.ORG) | Q(league__organization_id=org_id)
    )


def _is_site_admin(user: CustomUser) -> bool:
    return bool(user.is_staff or user.is_superuser)


class _AccessSets:
    def __init__(self) -> None:
        self._org_admin: dict[int, frozenset[int]] = {}
        self._org_staff: dict[int, frozenset[int]] = {}
        self._league_admin: dict[int, frozenset[int]] = {}
        self._league_staff: dict[int, frozenset[int]] = {}

    def org_admin(self, org: Organization) -> frozenset[int]:
        if org.pk not in self._org_admin:
            ids = set(org.admins.values_list("pk", flat=True))
            if org.owner_id is not None:
                ids.add(org.owner_id)
            self._org_admin[org.pk] = frozenset(ids)
        return self._org_admin[org.pk]

    def org_staff(self, org: Organization) -> frozenset[int]:
        if org.pk not in self._org_staff:
            ids = set(org.staff.values_list("pk", flat=True))
            self._org_staff[org.pk] = self.org_admin(org) | ids
        return self._org_staff[org.pk]

    def league_admin(self, league: League) -> frozenset[int]:
        if league.pk not in self._league_admin:
            ids = set(league.admins.values_list("pk", flat=True))
            if league.organization is not None:
                ids |= self.org_admin(league.organization)
            self._league_admin[league.pk] = frozenset(ids)
        return self._league_admin[league.pk]

    def league_staff(self, league: League) -> frozenset[int]:
        if league.pk not in self._league_staff:
            ids = set(league.staff.values_list("pk", flat=True))
            ids |= self.league_admin(league)
            if league.organization is not None:
                ids |= self.org_staff(league.organization)
            self._league_staff[league.pk] = frozenset(ids)
        return self._league_staff[league.pk]


def review_flags(
    viewer: CustomUser | None, rows: list[MmrChangeRequest]
) -> dict[int, bool]:
    if viewer is None or not viewer.is_authenticated:
        return {row.pk: False for row in rows}
    sets = _AccessSets()
    flags: dict[int, bool] = {}
    for row in rows:
        flags[row.pk] = _row_flag(viewer, row, sets)
    return flags


def _row_flag(viewer: CustomUser, row: MmrChangeRequest, sets: _AccessSets) -> bool:
    if not may_self_verify(viewer, row.subject_user_id):
        return False
    if row.target == MmrChangeRequest.Target.LEAGUE:
        if row.league is None:
            return False
        staff_ids = sets.league_staff(row.league)
        admin_ids = sets.league_admin(row.league)
    else:
        staff_ids = sets.org_staff(row.organization)
        admin_ids = sets.org_admin(row.organization)
    site = _is_site_admin(viewer)
    if not site and viewer.pk not in staff_ids:
        return False
    if viewer.is_superuser:
        return True
    subject = row.subject_user
    if _is_site_admin(subject) or subject.pk in staff_ids:
        return site or viewer.pk in admin_ids
    return True
