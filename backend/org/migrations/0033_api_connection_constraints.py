from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("org", "0032_backfill_api_connections")]

    operations = [
        migrations.AddConstraint(
            model_name="orgapitoken",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("legacy_credential", False), ("revoked_at__isnull", True)
                ),
                fields=("connection",),
                name="org_api_one_current_credential",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapiconnection",
            constraint=models.CheckConstraint(
                condition=models.Q(("config_version__gte", 1)),
                name="org_api_version_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapiconnection",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("interval_minutes__isnull", True),
                    models.Q(
                        ("interval_minutes__gte", 15), ("interval_minutes__lte", 10080)
                    ),
                    _connector="OR",
                ),
                name="org_api_interval_bounds",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapimmrdelivery",
            constraint=models.UniqueConstraint(
                fields=("connection", "org_user", "game_type", "revision"),
                name="org_api_mmr_delivery_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapipromotioneventbinding",
            constraint=models.UniqueConstraint(
                fields=("binding", "occasion_id"),
                name="org_api_promotion_occasion_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapisyncrun",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("kind", "mmr_pull"),
                    ("state__in", ["queued", "running", "partial"]),
                ),
                fields=("connection",),
                name="org_api_one_active_pull",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapisyncrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("request_count__lte", 100)),
                name="org_api_run_request_cap",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapisyncrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_count__lte", 10000)),
                name="org_api_run_row_cap",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapisyncrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("response_bytes__lte", 10485760)),
                name="org_api_run_byte_cap",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgapimmrpulltarget",
            constraint=models.UniqueConstraint(
                fields=("run", "org_user", "game_type"),
                name="org_api_pull_target_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="orgmmrrevisioncounter",
            constraint=models.UniqueConstraint(
                fields=("organization", "game_type"), name="org_mmr_counter_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="orgmmrsyncstate",
            constraint=models.UniqueConstraint(
                fields=("org_user", "game_type"), name="org_mmr_sync_state_unique"
            ),
        ),
    ]
