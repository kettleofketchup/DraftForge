from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

FIELD_MAP: dict[str, str] = {
    "draft_timer_enabled": "timer_enabled",
    "draft_grace_time_ms": "grace_time_ms",
    "draft_reserve_time_ms": "reserve_time_ms",
    "draft_timeout_action": "timeout_action",
    "hero_timer_enabled": "hero_timer_enabled",
    "hero_grace_time_ms": "hero_grace_time_ms",
    "hero_reserve_time_ms": "hero_reserve_time_ms",
}


def copy_tournament_options_to_events(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Event = apps.get_model("events", "Event")
    DraftOptions = apps.get_model("app", "DraftOptions")
    options_by_tournament = {
        o.tournament_id: o
        for o in DraftOptions.objects.filter(
            tournament_id__in=Event.objects.exclude(tournament=None).values(
                "tournament_id"
            )
        )
    }
    events = []
    for event in Event.objects.exclude(tournament=None).only(
        "id", "tournament_id", *FIELD_MAP
    ):
        options = options_by_tournament.get(event.tournament_id)
        if options is None:
            continue
        for event_field, option_field in FIELD_MAP.items():
            setattr(event, event_field, getattr(options, option_field))
        events.append(event)
    Event.objects.bulk_update(events, list(FIELD_MAP), batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("events", "0023_event_draft_grace_time_ms_and_more"),
    ]

    operations = [
        migrations.RunPython(copy_tournament_options_to_events, migrations.RunPython.noop),
    ]
