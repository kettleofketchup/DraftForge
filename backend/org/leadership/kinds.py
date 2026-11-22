from typing import Final

from django.db import models


class LeadershipKind(models.TextChoices):
    CAPTAINED = "captained", "Captained a team"
    PLACEMENT_1 = "placement_1", "Team placed 1st"
    PLACEMENT_2 = "placement_2", "Team placed 2nd"
    PLACEMENT_3 = "placement_3", "Team placed 3rd"
    DRAFT_COMPLETED = "draft_completed", "Draft completed"
    CAPTAIN_RATING = "captain_rating", "Captain rating"


RATED_KINDS: Final[tuple[LeadershipKind, ...]] = (
    LeadershipKind.CAPTAINED,
    LeadershipKind.PLACEMENT_1,
    LeadershipKind.PLACEMENT_2,
    LeadershipKind.PLACEMENT_3,
    LeadershipKind.DRAFT_COMPLETED,
)
FORMULA_KINDS: Final[tuple[LeadershipKind, ...]] = (LeadershipKind.CAPTAIN_RATING,)
DEFAULT_POINTS: Final[dict[str, int]] = {
    LeadershipKind.CAPTAINED.value: 5,
    LeadershipKind.PLACEMENT_1.value: 10,
    LeadershipKind.PLACEMENT_2.value: 6,
    LeadershipKind.PLACEMENT_3.value: 3,
    LeadershipKind.DRAFT_COMPLETED.value: 2,
}
PLACEMENT_KINDS: Final[dict[int, LeadershipKind]] = {
    1: LeadershipKind.PLACEMENT_1,
    2: LeadershipKind.PLACEMENT_2,
    3: LeadershipKind.PLACEMENT_3,
}
