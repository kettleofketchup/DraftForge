import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("app", "0096_squashed_0106"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="DraftTeam",
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
                        ("is_first_pick", models.BooleanField(blank=True, null=True)),
                        ("is_radiant", models.BooleanField(blank=True, null=True)),
                        ("reserve_time_remaining", models.IntegerField(default=90000)),
                        ("is_ready", models.BooleanField(default=False)),
                        ("is_connected", models.BooleanField(default=False)),
                        (
                            "tournament_team",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="hero_draft_teams",
                                to="app.team",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_draftteam",
                    },
                ),
                migrations.CreateModel(
                    name="HeroDraft",
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
                            "state",
                            models.CharField(
                                choices=[
                                    ("waiting_for_captains", "Waiting for Captains"),
                                    ("rolling", "Rolling"),
                                    ("choosing", "Choosing"),
                                    ("drafting", "Drafting"),
                                    ("paused", "Paused"),
                                    ("resuming", "Resuming"),
                                    ("completed", "Completed"),
                                    ("abandoned", "Abandoned"),
                                ],
                                default="waiting_for_captains",
                                max_length=32,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("paused_at", models.DateTimeField(blank=True, null=True)),
                        ("resuming_until", models.DateTimeField(blank=True, null=True)),
                        ("is_manual_pause", models.BooleanField(default=False)),
                        ("timer_enabled", models.BooleanField(default=True)),
                        ("grace_time_ms", models.IntegerField(default=30000)),
                        (
                            "game",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="herodraft",
                                to="app.game",
                            ),
                        ),
                        (
                            "roll_winner",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="won_rolls",
                                to="draft.draftteam",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_herodraft",
                    },
                ),
                migrations.AddField(
                    model_name="draftteam",
                    name="draft",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="draft_teams",
                        to="draft.herodraft",
                    ),
                ),
                migrations.CreateModel(
                    name="HeroDraftEvent",
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
                            "event_type",
                            models.CharField(
                                choices=[
                                    ("captain_connected", "Captain Connected"),
                                    ("captain_disconnected", "Captain Disconnected"),
                                    ("captain_ready", "Captain Ready"),
                                    ("draft_paused", "Draft Paused"),
                                    ("draft_resumed", "Draft Resumed"),
                                    ("roll_triggered", "Roll Triggered"),
                                    ("roll_result", "Roll Result"),
                                    ("choice_made", "Choice Made"),
                                    ("round_started", "Round Started"),
                                    ("hero_selected", "Hero Selected"),
                                    ("round_timeout", "Round Timeout"),
                                    ("draft_completed", "Draft Completed"),
                                ],
                                max_length=32,
                            ),
                        ),
                        ("metadata", models.JSONField(blank=True, default=dict)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "draft",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="events",
                                to="draft.herodraft",
                            ),
                        ),
                        (
                            "draft_team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="events",
                                to="draft.draftteam",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_herodraftevent",
                        "ordering": ["created_at"],
                    },
                ),
                migrations.CreateModel(
                    name="HeroDraftRound",
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
                        ("round_number", models.IntegerField()),
                        (
                            "action_type",
                            models.CharField(
                                choices=[("ban", "Ban"), ("pick", "Pick")], max_length=8
                            ),
                        ),
                        ("hero_id", models.IntegerField(blank=True, null=True)),
                        (
                            "state",
                            models.CharField(
                                choices=[
                                    ("planned", "Planned"),
                                    ("active", "Active"),
                                    ("completed", "Completed"),
                                ],
                                default="planned",
                                max_length=16,
                            ),
                        ),
                        ("grace_time_ms", models.IntegerField(default=30000)),
                        ("started_at", models.DateTimeField(blank=True, null=True)),
                        ("completed_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "draft",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rounds",
                                to="draft.herodraft",
                            ),
                        ),
                        (
                            "draft_team",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rounds",
                                to="draft.draftteam",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_herodraftround",
                        "ordering": ["round_number"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
