"""Org model signals.

- Blank an org's Discord server nicknames when its discord_server_id changes.
- Quarantine an account's imported SFG promotion receipts before it is
  deleted, however the delete happens (instance, queryset, admin, API), so
  a receipt never stays linked to a vanished user and ticks a later owner
  of the same Discord ID.
"""

from typing import Any

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from org.discord_names import reset_org_guild_nicknames
from org.models import Organization


@receiver(
    pre_save, sender="org.Organization", dispatch_uid="org_track_discord_server_id"
)
def track_org_discord_server_id(
    sender: type[Organization],
    instance: Organization,
    raw: bool = False,
    **kwargs: object,
) -> None:
    update_fields = kwargs.get("update_fields")
    if (
        raw
        or not instance.pk
        or (update_fields is not None and "discord_server_id" not in update_fields)
    ):
        instance._prior_discord_server_id = instance.discord_server_id
        return
    instance._prior_discord_server_id = (
        sender.objects.nocache()
        .filter(pk=instance.pk)
        .values_list("discord_server_id", flat=True)
        .first()
    )


@receiver(
    post_save, sender="org.Organization", dispatch_uid="org_reset_guild_nicknames"
)
def reset_guild_nicknames_on_server_change(
    sender: type[Organization],
    instance: Organization,
    created: bool = False,
    raw: bool = False,
    **kwargs: object,
) -> None:
    if raw or created:
        return
    prior = getattr(instance, "_prior_discord_server_id", instance.discord_server_id)
    current = instance.discord_server_id or None
    if (prior or None) == current:
        return
    reset_org_guild_nicknames(instance, enqueue=current is not None)


@receiver(
    pre_delete, sender="app.CustomUser", dispatch_uid="org_promo_identity_deleted"
)
def cancel_promotion_identity_on_user_delete(
    sender: type, instance: Any, **kwargs: object
) -> None:
    # local: keep app and integration models out of signal-module import time
    from org.integration.lifecycle import cancel_or_redact_promotion_identity

    cancel_or_redact_promotion_identity(instance)
