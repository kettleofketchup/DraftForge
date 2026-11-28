import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0032_orgleadershipsettings_captain_feedback_visible"),
    ]

    operations = [
        migrations.AddField(
            model_name="orgleadershipsettings",
            name="review_dms_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="CaptainReviewDraft",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("scores", models.JSONField(default=dict)),
                ("seeded_from_review_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event_captain",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_drafts",
                        to="org.eventcaptain",
                    ),
                ),
                (
                    "rater",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="captain_review_drafts",
                        to="org.orguser",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("event_captain", "rater"),
                        name="uniq_captain_review_draft",
                    )
                ],
            },
        ),
    ]
