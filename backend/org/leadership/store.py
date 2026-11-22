from org.models_leadership import OrgLeadershipSettings
from org.standing.scoring import RateParams, from_score5


def rate_params(settings: OrgLeadershipSettings) -> RateParams:
    return RateParams(
        half_life_days=settings.half_life_days,
        max_age_days=settings.max_age_days,
        prior=from_score5(settings.prior_rating),
        prior_strength=settings.prior_strength,
        min_count=1,
    )
