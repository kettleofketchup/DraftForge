from typing import Any

from django.db.models.signals import post_init, post_save
from django.dispatch import receiver

from common.game import GameType
from org.models import OrgUser, OrgUserGameMmr


@receiver(post_init, sender=OrgUser)
def remember_loaded_mmr(
    sender: type[OrgUser], instance: OrgUser, **kwargs: Any
) -> None:
    instance._loaded_mmr = instance.__dict__.get("mmr")


@receiver(post_save, sender=OrgUser)
def mirror_legacy_mmr_to_dota_row(
    sender: type[OrgUser],
    instance: OrgUser,
    created: bool,
    update_fields: frozenset[str] | None = None,
    **kwargs: Any,
) -> None:
    current = instance.__dict__.get("mmr")
    if created:
        sync = bool(current)
    elif update_fields is not None:
        sync = "mmr" in update_fields
    else:
        sync = current != getattr(instance, "_loaded_mmr", current)
    if not sync:
        return
    if current:
        OrgUserGameMmr.objects.update_or_create(
            org_user=instance, game_type=GameType.DOTA2, defaults={"mmr": current}
        )
    else:
        OrgUserGameMmr.objects.filter(
            org_user=instance, game_type=GameType.DOTA2
        ).delete()
    instance._loaded_mmr = current
    getattr(instance, "_prefetched_objects_cache", {}).pop("game_mmrs", None)
    instance.__dict__.pop("_org_mmrs_memo", None)
