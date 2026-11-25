"""Opt-in synthetic external contact fixtures for the promotion E2E specs.

Builds on the audience fixture (its Discord guild cache and members) and
binds the Features Test Org's upcoming event to a synthetic external occasion, so
the candidate list reports the integration as configured. It then stores
imported external receipts exactly as the import endpoint would, for four kinds of
candidate:

- ``external``: a member contacted in the external contact log only.
- ``local_and_external``: the audience fixture's locally messaged member, also
  contacted in the external contact log.
- ``discord_only``: a guild member without a DraftForge account.
- ``non_member``: a recent tournament player who is not an org member.

No PromoSend, award, account or membership is created for any of them, and no
real contact log, adaptor or Discord endpoint is contacted. All IDs are synthetic.
"""

from datetime import timedelta
from types import MappingProxyType
from typing import Any, Final
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from config.promotion_sync import OrgPromotionBinding, PromotionSyncConfig
from events.models import Event
from org.integration.receipts import _legacy_import_source_hash
from org.models import Organization, OrgUser
from org.models_promotion_sync import (
    AssociationState,
    ContactMethod,
    ContactReason,
    ExternalPromotionReceipt,
    PromotionContactOutbox,
    ReceiptSource,
)
from tests.data.org_features import FEATURES_ORG, ORG_FEATURES_PLAYERS
from tests.populate.promotion_audiences import GUILD_ID

OCCASION_ID: Final[int] = 7001
CONTACT_TZ: Final = ZoneInfo("America/New_York")
NON_MEMBER = ORG_FEATURES_PLAYERS[9]
_NOT_SET: Final = object()
_original_sync: Any = _NOT_SET

# key, audience ref (or None for the non-member), source contact ID, hours ago
RECEIPTS: Final[tuple[tuple[str, str | None, int, int], ...]] = (
    ("external", "week", 8101, 3),
    ("local_and_external", "messaged", 8102, 30),
    ("discord_only", "unlinked", 8103, 5),
    ("non_member", None, 8104, 50),
)


def restore_promotion_integration_settings() -> None:
    """Undo the binding and drop every receipt and outbox row of the org."""
    global _original_sync
    if _original_sync is not _NOT_SET:
        settings.PROMOTION_SYNC = _original_sync
        _original_sync = _NOT_SET
    ExternalPromotionReceipt.objects.filter(organization_id=FEATURES_ORG.pk).delete()
    PromotionContactOutbox.objects.filter(organization_id=FEATURES_ORG.pk).delete()


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
    now = timezone.now()
    refs: dict[str, Any] = {}
    for key, audience, contact_id, hours in RECEIPTS:
        if audience is None:
            ref = {"pk": NON_MEMBER.pk, "discord_id": NON_MEMBER.discord_id}
        else:
            ref = dict(audiences[audience])
        recorded_at = now - timedelta(hours=hours)
        entry = {
            "source_contact_id": str(contact_id),
            "event_id": str(event.pk),
            "discord_id": ref["discord_id"],
            "recorded_at": recorded_at,
            "contact_method": ContactMethod.DISCORD_DM.value,
            "linkage": "occasion",
        }
        org_user = (
            OrgUser.objects.nocache()
            .filter(organization=org, user_id=ref["pk"])
            .first()
            if ref["pk"] is not None
            else None
        )
        ExternalPromotionReceipt.objects.create(
            organization=org,
            source=ReceiptSource.CONTACT_LOG,
            source_contact_id=contact_id,
            event=event,
            discord_id=ref["discord_id"],
            recorded_at=recorded_at,
            contact_date_ny=recorded_at.astimezone(CONTACT_TZ).date(),
            contact_method=ContactMethod.DISCORD_DM,
            contact_reason=ContactReason.EVENT_INVITE,
            occasion_id=OCCASION_ID,
            forced=False,
            source_hash=_legacy_import_source_hash(entry),
            first_imported_at=now - timedelta(minutes=5),
            user_id=ref["pk"],
            org_user=org_user,
            association_state=(
                AssociationState.LINKED
                if ref["pk"] is not None
                else AssociationState.UNRESOLVED
            ),
            association_updated_at=now - timedelta(minutes=5),
        )
        refs[key] = {**ref, "source_contact_id": str(contact_id)}
    return refs
