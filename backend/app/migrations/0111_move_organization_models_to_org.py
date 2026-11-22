import django.db.models.deletion
import structlog
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

log = structlog.get_logger(__name__)

ORG_MODELS = ("organization", "orglog")


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in ORG_MODELS:
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
    relabel(apps, "app", "org")


def relabel_reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "org", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0110_orglog_conduct_actions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("events", "0035_retarget_organization_to_org"),
        ("opsnotices", "0003_retarget_organization_to_org"),
        ("org", "0014_move_organization_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="customuser",
                    name="default_organization",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_for_users",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="league",
                    name="organization",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leagues",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="profileclaimrequest",
                    name="organization",
                    field=models.ForeignKey(
                        help_text="Organization where the target profile is a member",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claim_requests",
                        to="org.organization",
                    ),
                ),
                migrations.DeleteModel(name="OrgLog"),
                migrations.DeleteModel(name="Organization"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
