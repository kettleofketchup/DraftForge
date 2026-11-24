import django.db.models
from django.db import migrations

import org.api_tokens.operations

MMR_ONLY = ["mmr:read", "mmr:write"]


def backfill_mmr_only(apps, schema_editor):
    """Every token that predates grants keeps exactly the MMR pair."""
    Token = apps.get_model("org", "OrgApiToken")
    Token.objects.update(operations=MMR_ONLY)


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0023_api_tokens"),
    ]

    operations = [
        migrations.AddField(
            model_name="orgapitoken",
            name="operations",
            field=django.db.models.JSONField(
                default=org.api_tokens.operations.default_operations,
                help_text="Granted operations, sorted (see org.api_tokens.operations)",
            ),
        ),
        migrations.RunPython(backfill_mmr_only, migrations.RunPython.noop),
    ]
