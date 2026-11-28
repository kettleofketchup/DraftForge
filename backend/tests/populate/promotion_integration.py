"""Opt-in synthetic external contact fixtures for the promotion E2E specs.

Builds on the audience fixture (its Discord guild cache and members) and
binds the Features Test Org's upcoming event to a synthetic external occasion, so
the candidate list reports the integration as configured. It then posts one
guild-wide batch through the real import, for four kinds of candidate:

- ``external``: a member contacted in the external contact log only. The
  contact names the Features Promoter, so it credits them a promotion point.
- ``local_and_external``: the audience fixture's locally messaged member, also
  contacted in the external contact log. The local send is made to earn its
  point first, so the import voids that point with a ``promo_void`` reversal.
- ``discord_only``: a guild member without a DraftForge account.
- ``non_member``: a recent tournament player who is not an org member.

The last three name no promoter, so each holds its (event, player) point
uncredited. The import creates no PromoSend, account or membership, and no
real contact log, adaptor or Discord endpoint is contacted. All IDs are
synthetic.
"""

from datetime import timedelta
from types import MappingProxyType
from typing import Any, Final
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from app.models import CustomUser
from config.promotion_sync import OrgPromotionBinding, PromotionSyncConfig
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry
from org.integration.contacts import import_contact_receipts
from org.integration.receipts import format_timestamp
from org.models import (
    Organization,
    OrgApiPromotionAdoption,
    OrgApiPromotionBinding,
    OrgApiPromotionEventBinding,
    OrgUser,
    PromoSend,
)
from org.models_promotion_sync import (
    ContactMethod,
    ContactReason,
    ExternalPromotionReceipt,
    PromotionContactOutbox,
    ReceiptSource,
)
from tests.data.org_features import FEATURES_ORG, OF_PROMOTER, ORG_FEATURES_PLAYERS
from tests.populate.promotion_audiences import GUILD_ID

OCCASION_ID: Final[int] = 7001
CONTACT_TZ: Final = ZoneInfo("America/New_York")
NON_MEMBER = ORG_FEATURES_PLAYERS[9]
_NOT_SET: Final = object()
_original_sync: Any = _NOT_SET

# key, audience ref (or None for the non-member), source contact ID, hours
# ago, promoter Discord ID (or None when the contact names nobody)
RECEIPTS: Final[tuple[tuple[str, str | None, int, int, str | None], ...]] = (
    ("external", "week", 8101, 3, OF_PROMOTER.discord_id),
    ("local_and_external", "messaged", 8102, 30, None),
    ("discord_only", "unlinked", 8103, 5, None),
    ("non_member", None, 8104, 50, None),
)


def restore_promotion_integration_settings() -> None:
    """Undo the binding and drop every receipt, outbox row and per-org
    promotion stream binding or adoption of the org."""
    global _original_sync
    if _original_sync is not _NOT_SET:
        settings.PROMOTION_SYNC = _original_sync
        _original_sync = _NOT_SET
    ExternalPromotionReceipt.objects.filter(organization_id=FEATURES_ORG.pk).delete()
    PromotionContactOutbox.objects.filter(organization_id=FEATURES_ORG.pk).delete()
    OrgApiPromotionEventBinding.objects.filter(
        binding__organization_id=FEATURES_ORG.pk
    ).delete()
    OrgApiPromotionBinding.objects.filter(organization_id=FEATURES_ORG.pk).delete()
    OrgApiPromotionAdoption.objects.filter(organization_id=FEATURES_ORG.pk).delete()


def seed_promotion_integration(
    org: Organization, event: Event, audiences: dict[str, Any]
) -> dict[str, Any]:
    global _original_sync
    if _original_sync is _NOT_SET:
        _original_sync = settings.PROMOTION_SYNC
    settings.PROMOTION_SYNC = PromotionSyncConfig(
        bindings=(
            OrgPromotionBinding(
                org_id=org.pk,
                guild_id=int(GUILD_ID),
                events=MappingProxyType({event.pk: OCCASION_ID}),
            ),
        )
    )
    OrgUser.objects.nocache().filter(organization=org, user_id=NON_MEMBER.pk).delete()
    _earn_local_point(org, event)
    now = timezone.now()
    refs: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    for key, audience, contact_id, hours, promoter in RECEIPTS:
        if audience is None:
            ref = {"pk": NON_MEMBER.pk, "discord_id": NON_MEMBER.discord_id}
        else:
            ref = dict(audiences[audience])
        recorded_at = now - timedelta(hours=hours)
        entries.append(
            {
                "source_contact_id": str(contact_id),
                "target_discord_id": ref["discord_id"],
                "promoter_discord_id": promoter,
                "recorded_at": format_timestamp(recorded_at),
                "contact_date_ny": recorded_at.astimezone(CONTACT_TZ)
                .date()
                .isoformat(),
                "contact_method": ContactMethod.DISCORD_DM.value,
                "contact_reason": ContactReason.EVENT_INVITE.value,
                "occasion_id": str(OCCASION_ID),
                "event_date": None,
                "forced": False,
            }
        )
        refs[key] = {
            **ref,
            "source_contact_id": str(contact_id),
            "promoter_discord_id": promoter,
        }
    ids = [contact_id for _, _, contact_id, _, _ in RECEIPTS]
    result = import_contact_receipts(
        org,
        {
            "source": ReceiptSource.CONTACT_LOG.value,
            "guild_id": GUILD_ID,
            "scan_started_at": format_timestamp(now),
            "range": {"after": str(min(ids) - 1), "through": str(max(ids))},
            "skipped_ids": [],
            "entries": entries,
        },
    )
    assert result["applied"] == len(RECEIPTS), result
    assert result["credited"] == 1 and result["voided_local"] == 1, result
    return refs


def _earn_local_point(org: Organization, event: Event) -> None:
    """Make the audience fixture's local send earn its point, as a send
    recorded before the external contact was imported would."""
    send = PromoSend.objects.nocache().get(organization=org, event=event)
    send.earns_points = True
    send.save(update_fields=["earns_points"])
    award_entry(
        org=org,
        user=CustomUser.objects.get(pk=send.sender_id),
        kind=ContributionKind.PROMO_MESSAGE,
        occurred_at=send.sent_at,
        event=event,
        promo_send=send,
    )
