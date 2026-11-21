from collections import defaultdict

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

from telemetry.logging import get_logger

log = get_logger(__name__)

STEAM_ID_64_BASE = 76561197960265728
STEAM_ACCOUNT_ID_MAX = 2**32 - 1
PROFILE_MODELS = ("PlayerDotaProfile", "PlayerDeadlockProfile")


def _account_id(raw: str | None) -> int | None:
    value = (raw or "").strip()
    if not (value.isascii() and value.isdigit()):
        return None
    account_id = int(value)
    return account_id if 0 < account_id <= STEAM_ACCOUNT_ID_MAX else None


def copy_profile_friend_ids(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Copy each user's profile Friend ID onto an empty steam_account_id.

    Skips users whose profiles disagree ("ambiguous") or whose ID another user
    holds or also claims ("taken").
    """
    CustomUser = apps.get_model("app", "CustomUser")
    empty_user_ids = set(
        CustomUser.objects.filter(steam_account_id__isnull=True).values_list(
            "pk", flat=True
        )
    )
    candidates: dict[int, set[int]] = defaultdict(set)
    for model_name in PROFILE_MODELS:
        model = apps.get_model("org", model_name)
        rows = (
            model.objects.exclude(unverified_friend_id="")
            .filter(org_user__user_id__in=empty_user_ids)
            .values_list("org_user__user_id", "unverified_friend_id")
        )
        for user_id, raw in rows:
            account_id = _account_id(raw)
            if account_id is not None:
                candidates[user_id].add(account_id)

    single: dict[int, int] = {}
    for user_id, values in sorted(candidates.items()):
        if len(values) == 1:
            single[user_id] = next(iter(values))
        else:
            _skip(user_id, "ambiguous", sorted(values))

    claims: dict[int, list[int]] = defaultdict(list)
    for user_id, account_id in single.items():
        claims[account_id].append(user_id)
    held = set(
        CustomUser.objects.filter(steam_account_id__in=claims.keys()).values_list(
            "steam_account_id", flat=True
        )
    )
    copied = 0
    for account_id, user_ids in sorted(claims.items()):
        if account_id in held or len(user_ids) > 1:
            for user_id in user_ids:
                _skip(user_id, "taken", [account_id])
            continue
        copied += CustomUser.objects.filter(
            pk=user_ids[0], steam_account_id__isnull=True
        ).update(
            steam_account_id=account_id, steamid=account_id + STEAM_ID_64_BASE
        )
    log.info(
        "steam_friend_id_backfill_done",
        system="app",
        subsystem="migrations",
        copied=copied,
    )


def _skip(user_id: int, reason: str, values: list[int]) -> None:
    log.warning(
        "steam_friend_id_backfill_skipped",
        system="app",
        subsystem="migrations",
        user_id=user_id,
        reason=reason,
        friend_ids=values,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0112_widen_steam_account_id"),
        ("org", "0014_move_organization_models_from_app"),
    ]

    operations = [
        migrations.RunPython(copy_profile_friend_ids, migrations.RunPython.noop),
    ]
