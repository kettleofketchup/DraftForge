"""Look up the trusted external binding for an org's event.

Bindings come only from ``settings.PROMOTION_SYNC``
(``config/promotion_sync.py``). Every lookup also checks the event belongs
to the org and the configured guild is the org's own Discord server, so a
stale or mistyped binding fails closed instead of mapping contacts into the
wrong guild.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from config.promotion_sync import OrgPromotionBinding, PromotionSyncConfig
from events.models import Event
from org.integration.errors import IntegrationError
from org.models import Organization


@dataclass(frozen=True)
class EventBinding:
    org_id: int
    guild_id: int
    event_id: int
    occasion_id: int


def _config() -> PromotionSyncConfig:
    return settings.PROMOTION_SYNC


def get_org_binding(org_id: int) -> OrgPromotionBinding:
    """The org's binding, checked against its Discord server.

    403 ``binding_missing`` when the org is not configured, 403
    ``binding_mismatch`` when the configured guild is not the org's server.
    """
    binding = _config().for_org(org_id)
    if binding is None:
        raise IntegrationError("binding_missing", 403)
    server_id = (
        Organization.objects.nocache()
        .filter(pk=org_id)
        .values_list("discord_server_id", flat=True)
        .first()
    )
    if (server_id or "").strip() != str(binding.guild_id):
        raise IntegrationError("binding_mismatch", 403)
    return binding


def get_event_binding(org_id: int, event_id: int) -> EventBinding:
    """The binding for one event of ``org_id``.

    404 ``not_found`` when the event does not exist in this org (whatever
    the configuration says), 403 ``binding_missing`` when the org or event
    is not bound, 403 ``binding_mismatch`` for a guild mismatch.
    """
    binding = _config().for_org(org_id)
    if binding is None:
        raise IntegrationError("binding_missing", 403)
    if not (
        Event.objects.nocache().filter(pk=event_id, organization_id=org_id).exists()
    ):
        raise IntegrationError("not_found", 404)
    occasion_id = binding.events.get(event_id)
    if occasion_id is None:
        raise IntegrationError("binding_missing", 403)
    org_binding = get_org_binding(org_id)
    return EventBinding(
        org_id=org_id,
        guild_id=org_binding.guild_id,
        event_id=event_id,
        occasion_id=occasion_id,
    )
