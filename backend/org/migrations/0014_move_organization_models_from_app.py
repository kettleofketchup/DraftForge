import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0110_orglog_conduct_actions"),
        ("org", "0013_conduct"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Organization",
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
                        ("name", models.CharField(db_index=True, max_length=255)),
                        (
                            "description",
                            models.TextField(blank=True, default="", max_length=10000),
                        ),
                        ("logo", models.URLField(blank=True, default="")),
                        ("discord_link", models.URLField(blank=True, default="")),
                        (
                            "discord_server_id",
                            models.CharField(
                                blank=True,
                                help_text="Discord server (guild) ID for fetching members",
                                max_length=20,
                                null=True,
                            ),
                        ),
                        (
                            "rules_template",
                            models.TextField(blank=True, default="", max_length=50000),
                        ),
                        (
                            "timezone",
                            models.CharField(default="America/New_York", max_length=50),
                        ),
                        (
                            "members_private",
                            models.BooleanField(
                                default=False,
                                help_text="Restrict the member list to org staff (hides it from regular members)",
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "admins",
                            models.ManyToManyField(
                                blank=True,
                                related_name="admin_organizations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "default_league",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="default_for_organization",
                                to="app.league",
                            ),
                        ),
                        (
                            "owner",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name="owned_organizations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "promoters",
                            models.ManyToManyField(
                                blank=True,
                                related_name="promoter_organizations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "staff",
                            models.ManyToManyField(
                                blank=True,
                                related_name="staff_organizations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Organization",
                        "verbose_name_plural": "Organizations",
                        "db_table": "app_organization",
                        "ordering": ["name"],
                        "indexes": [
                            models.Index(
                                fields=["created_at"],
                                name="app_organiz_created_557442_idx",
                            )
                        ],
                    },
                ),
                migrations.CreateModel(
                    name="OrgLog",
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
                            "action",
                            models.CharField(
                                choices=[
                                    ("add_admin", "Add Admin"),
                                    ("remove_admin", "Remove Admin"),
                                    ("add_staff", "Add Staff"),
                                    ("remove_staff", "Remove Staff"),
                                    ("add_member", "Add Member"),
                                    ("transfer_ownership", "Transfer Ownership"),
                                    ("create", "Create Organization"),
                                    ("update", "Update Organization"),
                                    ("delete", "Delete Organization"),
                                    ("approve_claim", "Approve Profile Claim"),
                                    ("reject_claim", "Reject Profile Claim"),
                                    ("set_mmr", "Set MMR"),
                                    ("enable_feature", "Enable Feature"),
                                    ("disable_feature", "Disable Feature"),
                                    ("add_promoter", "Add Promoter"),
                                    ("remove_promoter", "Remove Promoter"),
                                    ("set_point_value", "Set Point Value"),
                                    ("rescore", "Rescore Contributions"),
                                    ("award_points", "Award Points"),
                                    ("edit_award", "Edit Award"),
                                    ("delete_award", "Delete Award"),
                                    ("complete_event", "Complete Event"),
                                    ("reopen_event", "Reopen Event"),
                                    ("set_event_staff", "Set Event Staff"),
                                    (
                                        "delete_user_contributions",
                                        "Delete User Contributions",
                                    ),
                                    ("set_attendance", "Set Attendance"),
                                    ("finalize_attendance", "Finalize Attendance"),
                                    ("void_attendance", "Void Attendance"),
                                ],
                                max_length=50,
                            ),
                        ),
                        ("details", models.JSONField(blank=True, default=dict)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "actor",
                            models.ForeignKey(
                                help_text="User who performed the action",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="org_actions_performed",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "organization",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="logs",
                                to="org.organization",
                            ),
                        ),
                        (
                            "target_user",
                            models.ForeignKey(
                                blank=True,
                                help_text="User affected by the action (if applicable)",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="org_actions_received",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Organization Log",
                        "verbose_name_plural": "Organization Logs",
                        "db_table": "app_orglog",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(
                                fields=["organization", "-created_at"],
                                name="app_orglog_organiz_b8ea3f_idx",
                            )
                        ],
                    },
                ),
                migrations.AlterField(
                    model_name="orguser",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="contributionpointvalue",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="point_values",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="contributionentry",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contribution_entries",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="orgfeature",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="features",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="promotemplate",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promo_templates",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="promosend",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promo_sends",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="orgsettings",
                    name="organization",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="settings",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="orgconductsettings",
                    name="organization",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conduct_settings",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="attendanceoutcome",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_outcomes",
                        to="org.organization",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
