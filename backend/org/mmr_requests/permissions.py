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
