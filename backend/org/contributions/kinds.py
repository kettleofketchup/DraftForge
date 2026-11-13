from django.db import models


class ContributionKind(models.TextChoices):
    PROMO_MESSAGE = "promo_message", "Promo message"
    EVENT_HOST = "event_host", "Event host"
    EVENT_HELPER = "event_helper", "Event helper"
    MANUAL = "manual", "Manual award"


EVENT_STAFF_KINDS: tuple[ContributionKind, ...] = (
    ContributionKind.EVENT_HOST,
    ContributionKind.EVENT_HELPER,
)
RATED_KINDS: tuple[ContributionKind, ...] = (
    ContributionKind.PROMO_MESSAGE,
    ContributionKind.EVENT_HOST,
    ContributionKind.EVENT_HELPER,
)
DEFAULT_POINTS: dict[str, int] = {
    ContributionKind.PROMO_MESSAGE.value: 1,
    ContributionKind.EVENT_HOST.value: 10,
    ContributionKind.EVENT_HELPER.value: 5,
}
