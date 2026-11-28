from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def backfill_connections(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    alias = schema_editor.connection.alias
    Token = apps.get_model("org", "OrgApiToken")
    Connection = apps.get_model("org", "OrgApiConnection")
    GameMmr = apps.get_model("org", "OrgUserGameMmr")
    State = apps.get_model("org", "OrgMmrSyncState")
    Counter = apps.get_model("org", "OrgMmrRevisionCounter")

    stream_ids: dict[int, int] = {}
    for token in Token.objects.using(alias).order_by("pk").iterator(chunk_size=500):
        promotion = "promotion:import" in token.operations
        connection_id = stream_ids.get(token.organization_id) if promotion else None
        if connection_id is None:
            connection = Connection.objects.using(alias).create(
                organization_id=token.organization_id,
                name=token.name,
                created_by_id=token.user_id,
                updated_by_id=token.user_id,
                enabled=True,
                inbound_enabled=True,
                operations=token.operations,
                legacy_backfilled=True,
                legacy_multi_credential=promotion,
            )
            Connection.objects.using(alias).filter(pk=connection.pk).update(
                created_at=token.created_at
            )
            connection_id = connection.pk
            if promotion:
                stream_ids[token.organization_id] = connection_id
        else:
            connection = Connection.objects.using(alias).get(pk=connection_id)
            grants = sorted(set(connection.operations) | set(token.operations))
            Connection.objects.using(alias).filter(pk=connection_id).update(operations=grants)
        Token.objects.using(alias).filter(pk=token.pk).update(
            connection_id=connection_id, legacy_credential=True, issued_by_id=token.user_id
        )

    for mmr in GameMmr.objects.using(alias).select_related("org_user").iterator(chunk_size=500):
        State.objects.using(alias).create(
            org_user_id=mmr.org_user_id,
            game_type=mmr.game_type,
            revision=0,
            value=mmr.mmr,
            verified_at=mmr.verified_at,
        )
        Counter.objects.using(alias).get_or_create(
            organization_id=mmr.org_user.organization_id,
            game_type=mmr.game_type,
            defaults={"revision": 0},
        )


class Migration(migrations.Migration):
    dependencies = [("org", "0032_api_connections")]

    operations = [migrations.RunPython(backfill_connections, migrations.RunPython.noop)]
