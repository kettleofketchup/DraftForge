from org.leadership.constants import DEFAULT_TRAITS
from org.models import Organization
from org.models_leadership import CaptainTrait, OrgLeadershipSettings
from org.standing.scoring import RateParams, from_score5


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def get_leadership_settings(
    org: Organization | int, *, create: bool = False
) -> OrgLeadershipSettings:
    org_id = _org_id(org)
    row = OrgLeadershipSettings.objects.filter(organization_id=org_id).first()
    if row is not None:
        return row
    if create:
        row, _ = OrgLeadershipSettings.objects.nocache().get_or_create(
            organization_id=org_id
        )
        return row
    return OrgLeadershipSettings(organization_id=org_id)


def rate_params(settings: OrgLeadershipSettings) -> RateParams:
    return RateParams(
        half_life_days=settings.half_life_days,
        max_age_days=settings.max_age_days,
        prior=from_score5(settings.prior_rating),
        prior_strength=settings.prior_strength,
        min_count=1,
    )


def default_traits(org_id: int) -> list[CaptainTrait]:
    return [
        CaptainTrait(organization_id=org_id, key=key, label=label, order=i)
        for i, (key, label) in enumerate(DEFAULT_TRAITS)
    ]


def effective_traits(org: Organization | int) -> list[CaptainTrait]:
    org_id = _org_id(org)
    rows = list(CaptainTrait.objects.nocache().filter(organization_id=org_id))
    return rows or default_traits(org_id)


def ensure_traits(org: Organization | int) -> list[CaptainTrait]:
    """Materialise the default traits on first use; call inside the write's atomic block."""
    org_id = _org_id(org)
    rows = CaptainTrait.objects.nocache().filter(organization_id=org_id)
    if not rows.exists():
        CaptainTrait.objects.bulk_create(default_traits(org_id), ignore_conflicts=True)
    return list(rows.all())


def active_traits(traits: list[CaptainTrait]) -> list[CaptainTrait]:
    return [t for t in traits if t.active]
