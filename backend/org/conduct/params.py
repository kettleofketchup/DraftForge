from dataclasses import dataclass

from org.models_conduct import OrgConductSettings
from org.standing.scoring import RateParams


@dataclass(frozen=True, slots=True)
class ConductParams:
    rate: RateParams
    late_cancel_weight: float


def rate_params(settings: OrgConductSettings) -> RateParams:
    return RateParams(
        half_life_days=settings.half_life_days,
        max_age_days=settings.max_age_days,
        prior=float(settings.prior_show_rate),
        prior_strength=float(settings.prior_strength),
        min_count=settings.min_events,
    )


def conduct_params(settings: OrgConductSettings) -> ConductParams:
    return ConductParams(
        rate=rate_params(settings),
        late_cancel_weight=float(settings.late_cancel_weight),
    )
