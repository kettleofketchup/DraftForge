import django.db.models.deletion
from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import OuterRef, Subquery

DOTA2 = 1


def backfill_dota_verified_at(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUserGameMmr = apps.get_model("org", "OrgUserGameMmr")
    last_verified = OrgUser.objects.filter(pk=OuterRef("org_user_id")).values(
        "dota_mmr_last_verified"
    )[:1]
    updated = OrgUserGameMmr.objects.filter(
        game_type=DOTA2,
        verified_at__isnull=True,
        org_user__has_active_dota_mmr=True,
        org_user__dota_mmr_last_verified__isnull=False,
    ).update(verified_at=Subquery(last_verified))
    print(f"\n  org_user_game_mmr verification backfill: {updated} Dota 2 rows")


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0022_retarget_tournament_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="orgusergamemmr",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orgusergamemmr",
            name="verified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_dota_verified_at, migrations.RunPython.noop),
    ]
