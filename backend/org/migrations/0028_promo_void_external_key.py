from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import OuterRef, Subquery


def freeze_external_keys(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Best-effort backfill from each void's current receipt target."""
    Entry = apps.get_model("org", "ContributionEntry")
    Receipt = apps.get_model("org", "ExternalPromotionReceipt")
    receipt_key = (
        Receipt.objects.using(schema_editor.connection.alias)
        .filter(pk=OuterRef("external_contact_id"))
        .values("discord_id")[:1]
    )
    Entry.objects.using(schema_editor.connection.alias).filter(
        kind="promo_void",
        external_contact__isnull=False,
        reversal_of__promo_send__isnull=False,
    ).update(external_point_discord_id=Subquery(receipt_key))


class Migration(migrations.Migration):
    dependencies = [("org", "0027_promotion_sync_receipts")]

    operations = [
        migrations.AddField(
            model_name="contributionentry",
            name="external_point_discord_id",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.RunPython(freeze_external_keys, migrations.RunPython.noop),
    ]
