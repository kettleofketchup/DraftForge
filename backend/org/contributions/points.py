from app.models import Organization
from org.contributions.kinds import DEFAULT_POINTS
from org.models import ContributionPointValue


def points_for(org: Organization, kind: str) -> int:
    value = (
        ContributionPointValue.objects.nocache()
        .filter(organization=org, kind=str(kind))
        .values_list("points", flat=True)
        .first()
    )
    return DEFAULT_POINTS[str(kind)] if value is None else value
