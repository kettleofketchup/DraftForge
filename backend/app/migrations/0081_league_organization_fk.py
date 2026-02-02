# Generated manually - Convert League.organizations M2M back to League.organization FK

import django.db.models.deletion
from django.db import migrations, models


def copy_m2m_to_fk(apps, schema_editor):
    """Copy first organization from M2M to FK field."""
    League = apps.get_model("app", "League")

    for league in League.objects.prefetch_related("organizations").all():
        first_org = league.organizations.first()
        if first_org:
            league.organization = first_org
            league.save(update_fields=["organization"])


def copy_fk_to_m2m(apps, schema_editor):
    """Reverse: copy FK to M2M field."""
    League = apps.get_model("app", "League")

    for league in League.objects.select_related("organization").all():
        if league.organization:
            league.organizations.add(league.organization)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0080_profile_claim_request"),
    ]

    operations = [
        # Step 1: Add the organization FK field
        migrations.AddField(
            model_name="league",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="leagues",
                to="app.organization",
            ),
        ),
        # Step 2: Copy data from M2M to FK
        migrations.RunPython(copy_m2m_to_fk, copy_fk_to_m2m),
        # Step 3: Remove the M2M field
        migrations.RemoveField(
            model_name="league",
            name="organizations",
        ),
    ]
