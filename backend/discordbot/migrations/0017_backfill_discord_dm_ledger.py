from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.utils import timezone

CHUNK = 500
FAKE_MESSAGE_ID = "test-fake-message-id"
REMINDER_DM_TYPE = 1
TOURNAMENT_DM_SOURCE = "tournament_dm"
KIND_BY_NOTIFICATION = {
    "draft_link": "tournament_draft_link",
    "herodraft_link": "tournament_herodraft_link",
}


def _chunks(rows: Iterable[Any]) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for row in rows:
        batch.append(row)
        if len(batch) == CHUNK:
            yield batch
            batch = []
    if batch:
        yield batch


def _claim_message_id(message_id: str | None, seen: set[str]) -> str | None:
    if not message_id or message_id in seen:
        return None
    seen.add(message_id)
    return message_id


def _from_event_dm(
    model: Any, row: Any, now: datetime, seen_message_ids: set[str]
) -> Any:
    if row.dm_type != REMINDER_DM_TYPE:
        raise AssertionError(
            f"DiscordEventDM {row.pk} has unexpected dm_type {row.dm_type}"
        )
    user = row.org_user.user
    fields: dict[str, Any] = {
        "kind": "signup_reminder",
        "idempotency_key": f"legacy:discordeventdm:{row.pk}",
        "backfilled_from": "discordeventdm",
        "recipient_id": user.pk,
        "discord_user_id": user.discordId or "",
        "organization_id": row.org_user.organization_id,
        "subject_type": "event",
        "subject_id": row.discord_event.event_id,
        "retryable": False,
        "attempts": 1,
        "created_at": row.created_at,
        "claimed_at": row.created_at,
    }
    if row.delivered and row.message_id == FAKE_MESSAGE_ID:
        fields.update(status="skipped_test_mode", finished_at=row.sent_at or now)
    elif row.delivered:
        fields.update(
            status="sent",
            sent_at=row.sent_at,
            finished_at=row.sent_at or now,
            discord_message_id=_claim_message_id(row.message_id, seen_message_ids),
        )
    else:
        fields.update(
            status="failed", error="legacy: not delivered", finished_at=now
        )
    return model(**fields)


def _message_log_org(row: Any, event_model: Any) -> int | None:
    tlog = row.tournament_log
    if tlog is None:
        return None
    league = tlog.tournament.league
    if league is not None and league.organization_id is not None:
        return league.organization_id
    return (
        event_model.objects.filter(tournament_id=tlog.tournament_id)
        .order_by("pk")
        .values_list("organization_id", flat=True)
        .first()
    )


def _from_message_log(
    model: Any, row: Any, event_model: Any, seen_message_ids: set[str]
) -> Any:
    tlog = row.tournament_log
    kind = KIND_BY_NOTIFICATION.get(tlog.notification_type) if tlog else None
    fields: dict[str, Any] = {
        "kind": kind or "tournament_draft_link",
        "context": {} if kind else {"legacy_kind_unknown": True},
        "idempotency_key": f"legacy:discordmessagelog:{row.pk}",
        "backfilled_from": "discordmessagelog",
        "discord_user_id": "",
        "organization_id": _message_log_org(row, event_model),
        "tournament_log_id": row.tournament_log_id,
        "discord_channel_id": row.channel_id or "",
        "http_status": row.status_code,
        "retryable": False,
        "attempts": 1,
        "created_at": row.created_at,
        "claimed_at": row.created_at,
        "finished_at": row.created_at,
    }
    if tlog is not None:
        fields.update(subject_type="tournament", subject_id=tlog.tournament_id)
    if row.success:
        fields.update(
            status="sent",
            sent_at=row.created_at,
            discord_message_id=_claim_message_id(
                row.discord_message_id, seen_message_ids
            ),
        )
    elif row.success is False:
        fields.update(status="failed", error="legacy: send failed")
    else:
        fields.update(status="unknown", error="legacy: send outcome unknown")
    return model(**fields)


def backfill(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    DiscordDM = apps.get_model("discordbot", "DiscordDM")
    DiscordEventDM = apps.get_model("discordbot", "DiscordEventDM")
    DiscordMessageLog = apps.get_model("discordbot", "DiscordMessageLog")
    Event = apps.get_model("events", "Event")
    now = timezone.now()
    seen_message_ids = set(
        DiscordDM.objects.exclude(discord_message_id__isnull=True).values_list(
            "discord_message_id", flat=True
        )
    )

    event_dms = (
        DiscordEventDM.objects.filter(ledger_entry__isnull=True)
        .select_related("org_user__user", "discord_event")
        .order_by("pk")
        .iterator(chunk_size=CHUNK)
    )
    for chunk in _chunks(event_dms):
        keys = {f"legacy:discordeventdm:{row.pk}": row for row in chunk}
        existing = set(
            DiscordDM.objects.filter(idempotency_key__in=keys).values_list(
                "idempotency_key", flat=True
            )
        )
        DiscordDM.objects.bulk_create(
            [
                _from_event_dm(DiscordDM, row, now, seen_message_ids)
                for key, row in keys.items()
                if key not in existing
            ]
        )
        ids = dict(
            DiscordDM.objects.filter(idempotency_key__in=keys).values_list(
                "idempotency_key", "pk"
            )
        )
        for key, row in keys.items():
            row.ledger_entry_id = ids[key]
        DiscordEventDM.objects.bulk_update(chunk, ["ledger_entry"])

    logs = (
        DiscordMessageLog.objects.filter(source=TOURNAMENT_DM_SOURCE)
        .select_related("tournament_log__tournament__league")
        .order_by("pk")
        .iterator(chunk_size=CHUNK)
    )
    for chunk in _chunks(logs):
        keys = {f"legacy:discordmessagelog:{row.pk}": row for row in chunk}
        existing = set(
            DiscordDM.objects.filter(idempotency_key__in=keys).values_list(
                "idempotency_key", flat=True
            )
        )
        DiscordDM.objects.bulk_create(
            [
                _from_message_log(DiscordDM, row, Event, seen_message_ids)
                for key, row in keys.items()
                if key not in existing
            ]
        )


def noop(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "0016_discord_dm_ledger"),
        ("events", "0040_retarget_tournament_to_tournament"),
        ("league", "0003_move_league_models_from_app"),
        ("tournament", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill, noop)]
