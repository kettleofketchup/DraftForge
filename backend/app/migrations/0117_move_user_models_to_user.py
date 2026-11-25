import structlog
from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

log = structlog.get_logger(__name__)

USER_MODELS = ("positionsmodel", "profileclaimrequest")


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in USER_MODELS:
        source = content_type.objects.filter(app_label=src, model=model)
        if content_type.objects.filter(app_label=dst, model=model).exists():
            if source.exists():
                log.warning(
                    "contenttype_relabel_skipped",
                    system="migrations",
                    subsystem="contenttypes",
                    model=model,
                    direction=f"{src}->{dst}",
                )
            continue
        source.update(app_label=dst)


def relabel_forward(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "app", "user")


def relabel_reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "user", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0116_customuser_steam_account_verified"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("user", "0005_move_user_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="ProfileClaimRequest"),
                migrations.DeleteModel(name="PositionsModel"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
