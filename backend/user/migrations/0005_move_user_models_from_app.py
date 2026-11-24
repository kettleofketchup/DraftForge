import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0004_backfill_game_profiles"),
        ("app", "0115_move_tournament_models_to_tournament"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("org", "0022_retarget_tournament_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PositionsModel",
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
                        (
                            "carry",
                            models.IntegerField(
                                default=0,
                                help_text="Rank of the carry position from 0 (No play) to 5 (best)",
                            ),
                        ),
                        (
                            "mid",
                            models.IntegerField(
                                default=0,
                                help_text="Rank of the mid position from 0 (No play) to 5 (best)",
                            ),
                        ),
                        (
                            "offlane",
                            models.IntegerField(
                                default=0,
                                help_text="Rank of the offlane position from 0 (No play) to 5 (best)",
                            ),
                        ),
                        (
                            "soft_support",
                            models.IntegerField(
                                default=0,
                                help_text="Rank of the soft support position from 0 (No play) to 5 (best)",
                            ),
                        ),
                        (
                            "hard_support",
                            models.IntegerField(
                                default=0,
                                help_text="Rank of the hard support position from 0 (No play) to 5 (best)",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_positionsmodel",
                    },
                ),
                migrations.CreateModel(
                    name="ProfileClaimRequest",
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
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "Pending"),
                                    ("approved", "Approved"),
                                    ("rejected", "Rejected"),
                                ],
                                db_index=True,
                                default="pending",
                                max_length=20,
                            ),
                        ),
                        (
                            "rejection_reason",
                            models.TextField(
                                blank=True,
                                help_text="Reason for rejection (if rejected)",
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "claimer",
                            models.ForeignKey(
                                help_text="User requesting to claim the profile (has Discord ID)",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="claim_requests_made",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "organization",
                            models.ForeignKey(
                                help_text="Organization where the target profile is a member",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="claim_requests",
                                to="org.organization",
                            ),
                        ),
                        (
                            "reviewed_by",
                            models.ForeignKey(
                                blank=True,
                                help_text="Admin who approved/rejected the request",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="claim_requests_reviewed",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "target_user",
                            models.ForeignKey(
                                help_text="Profile being claimed (has Steam ID, no Discord). NULL after merge.",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="claim_requests_received",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_profileclaimrequest",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(
                                fields=["organization", "status", "-created_at"],
                                name="app_profile_organiz_4b1a91_idx",
                            ),
                            models.Index(
                                fields=["claimer", "status"],
                                name="app_profile_claimer_2ce297_idx",
                            ),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                condition=models.Q(("status", "pending")),
                                fields=("claimer", "target_user"),
                                name="unique_pending_claim_request",
                            )
                        ],
                    },
                ),
                migrations.AlterField(
                    model_name="dotauserprofile",
                    name="positions",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="user.positionsmodel",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
