from typing import Final

from django.db import models

MIN_RELEASE_REVIEWS: Final[int] = 2
MIN_EVENT_AGGREGATE_REVIEWS: Final[int] = 3
MAX_ACTIVE_TRAITS: Final[int] = 8
SCORE_MIN: Final[int] = 1
SCORE_MAX: Final[int] = 5
REASON_MIN_LENGTH: Final[int] = 3
REASON_MAX_LENGTH: Final[int] = 500

DEFAULT_TRAITS: Final[tuple[tuple[str, str], ...]] = (
    ("communication", "Communication"),
    ("drafting", "Drafting"),
    ("composure", "Composure"),
    ("sportsmanship", "Sportsmanship"),
)

SETTINGS_DEFAULTS: Final[dict[str, int | float | bool]] = {
    "review_window_hours": 72,
    "rating_max_points": 10,
    "rating_min_reviewers": 2,
    "ranked_min_reviews": 3,
    "prior_rating": 3.0,
    "prior_strength": 2.0,
    "half_life_days": 180,
    "max_age_days": 730,
    "leaderboard_public": False,
}

SETTINGS_RANGES: Final[dict[str, tuple[int | float, int | float]]] = {
    "review_window_hours": (1, 336),
    "rating_max_points": (0, 100),
    "rating_min_reviewers": (MIN_RELEASE_REVIEWS, 20),
    "ranked_min_reviews": (1, 50),
    "prior_rating": (1.0, 5.0),
    "prior_strength": (0.0, 20.0),
    "half_life_days": (7, 730),
    "max_age_days": (30, 1825),
}

EDITABLE_SETTINGS_FIELDS: Final[tuple[str, ...]] = tuple(SETTINGS_DEFAULTS)


class VoidKind(models.TextChoices):
    WITHDRAWN = "withdrawn", "Withdrawn by rater"
    LIFECYCLE = "lifecycle", "Event reopened or cancelled"
    MODERATED = "moderated", "Voided by staff"


RATER_REVIVABLE: Final[frozenset[str]] = frozenset(
    {VoidKind.WITHDRAWN.value, VoidKind.LIFECYCLE.value}
)
