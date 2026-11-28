import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discordbot", "0015_retarget_tournament_models"),
        ("events", "0043_discord_post_channels"),
    ]

    operations = [
        migrations.CreateModel(
            name="SignupPostDeliveryState",
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
                ("generation", models.PositiveIntegerField(default=0)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(null=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("reserved", "Reserved"),
                            ("sending", "Sending"),
                            ("delivered", "Delivered"),
                            ("exhausted", "Exhausted"),
                            ("uncertain", "Uncertain"),
                        ],
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("attempt_token", models.UUIDField(null=True)),
                ("reserved_at", models.DateTimeField(null=True)),
                ("active_log_id", models.IntegerField(null=True)),
                ("receipt", models.JSONField(null=True)),
                ("last_failure_category", models.CharField(max_length=32, null=True)),
                ("last_failure_status", models.IntegerField(null=True)),
                ("last_failure_code", models.IntegerField(null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signup_delivery_state",
                        to="events.event",
                    ),
                ),
            ],
        ),
    ]
