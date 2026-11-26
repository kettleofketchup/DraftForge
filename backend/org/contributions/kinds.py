from django.db import models


class ContributionKind(models.TextChoices):
    PROMO_MESSAGE = "promo_message", "Promo message"
    EVENT_HOST = "event_host", "Event host"
    EVENT_HELPER = "event_helper", "Event helper"
    MANUAL = "manual", "Manual award"
    PROMO_VOID = "promo_void", "Promotion point voided"
    PROMO_RESTORE = "promo_restore", "Promotion point restored"


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
# Ledger reversals of a promotion point: never rated, never defaulted, and
# never counted as entries of their own.
REVERSAL_KINDS: frozenset[ContributionKind] = frozenset(
    {ContributionKind.PROMO_VOID, ContributionKind.PROMO_RESTORE}
)
