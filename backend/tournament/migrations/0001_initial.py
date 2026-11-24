import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("app", "0114_copy_profile_friend_ids"),
        ("events", "0038_ready_check_recipient_help_text"),
        ("league", "0003_move_league_models_from_app"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Team",
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
                        ("name", models.CharField(max_length=255)),
                        (
                            "draft_order",
                            models.PositiveSmallIntegerField(
                                blank=True,
                                default=0,
                                help_text="Order in which a team picks their players in the draft",
                                null=True,
                            ),
                        ),
                        ("current_points", models.IntegerField(blank=True, default=0)),
                        (
                            "placement",
                            models.PositiveSmallIntegerField(
                                blank=True,
                                help_text="Final tournament placement (1=winner, 2=runner-up, etc.)",
                                null=True,
                            ),
                        ),
                        (
                            "draft_reserve_ms",
                            models.IntegerField(blank=True, null=True),
                        ),
                        ("draft_is_ready", models.BooleanField(default=False)),
                        ("draft_is_connected", models.BooleanField(default=False)),
                        ("draft_has_connected", models.BooleanField(default=False)),
                        (
                            "captain",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="teams_as_captain",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "deputy_captain",
                            models.ForeignKey(
                                blank=True,
                                help_text="Next in line for captain if captain is removed",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="teams_as_deputy_captain",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "dropin_members",
                            models.ManyToManyField(
                                blank=True,
                                related_name="teams_as_dropin",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "league_users",
                            models.ManyToManyField(
                                blank=True,
                                help_text="Team members as LeagueUser (for org-scoped MMR)",
                                related_name="teams",
                                to="league.leagueuser",
                            ),
                        ),
                        (
                            "left_members",
                            models.ManyToManyField(
                                blank=True,
                                related_name="teams_as_left",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "members",
                            models.ManyToManyField(
                                blank=True,
                                related_name="teams_as_member",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_team",
                    },
                ),
                migrations.CreateModel(
                    name="Tournament",
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
                        ("name", models.CharField(max_length=255)),
                        (
                            "date_played",
                            models.DateTimeField(
                                help_text="Tournament date and time (stored in UTC)"
                            ),
                        ),
                        (
                            "timezone",
                            models.CharField(
                                default="UTC",
                                help_text="Tournament timezone (e.g., 'America/New_York', 'Europe/London')",
                                max_length=50,
                            ),
                        ),
                        (
                            "state",
                            models.CharField(
                                choices=[
                                    ("future", "Future"),
                                    ("in_progress", "In Progress"),
                                    ("past", "Past"),
                                ],
                                default="future",
                                max_length=20,
                            ),
                        ),
                        (
                            "tournament_type",
                            models.CharField(
                                choices=[
                                    ("single_elimination", "Single Elimination"),
                                    ("double_elimination", "Double Elimination"),
                                    ("swiss", "Swiss Bracket"),
                                ],
                                default="double_elimination",
                                max_length=30,
                            ),
                        ),
                        (
                            "steam_league_id",
                            models.IntegerField(
                                blank=True,
                                db_column="league_id",
                                default=None,
                                help_text="Steam league ID for match linking",
                                null=True,
                            ),
                        ),
                        (
                            "game_type",
                            models.IntegerField(
                                choices=[(1, "Dota 2"), (2, "Deadlock")], default=1
                            ),
                        ),
                        (
                            "draft_type",
                            models.CharField(
                                choices=[
                                    ("snake", "Snake"),
                                    ("normal", "Normal"),
                                    ("shuffle", "Shuffle"),
                                ],
                                default="shuffle",
                                max_length=10,
                            ),
                        ),
                        ("people_per_team", models.IntegerField(default=5)),
                        ("number_of_teams", models.IntegerField(blank=True, null=True)),
                        (
                            "game_mode",
                            models.CharField(
                                choices=[
                                    ("normal", "Normal"),
                                    ("captains_mode", "Captain's Mode"),
                                    ("turbo", "Turbo"),
                                    ("custom", "Custom Lobby"),
                                ],
                                default="normal",
                                max_length=20,
                            ),
                        ),
                        (
                            "custom_game_name",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Custom game/lobby name (for custom game mode)",
                                max_length=255,
                            ),
                        ),
                        (
                            "captains_draft_time",
                            models.IntegerField(
                                default=10,
                                help_text="Seconds per draft pick in Captain's Mode",
                            ),
                        ),
                        (
                            "lobby_steam_league_id",
                            models.IntegerField(
                                blank=True,
                                help_text="Steam league ID for Dota 2 lobby ticket",
                                null=True,
                            ),
                        ),
                        ("auto_create_hero_drafts", models.BooleanField(default=False)),
                        ("discord_send_draft_link", models.BooleanField(default=True)),
                        (
                            "discord_send_herodraft_link",
                            models.BooleanField(default=True),
                        ),
                        (
                            "dota_lobby_mode",
                            models.CharField(
                                choices=[
                                    ("off", "Off"),
                                    ("manual", "Manual"),
                                    ("auto", "Automatic"),
                                ],
                                default="off",
                                max_length=8,
                            ),
                        ),
                        (
                            "dota_lobby_launch",
                            models.CharField(
                                choices=[("manual", "Manual"), ("auto", "Automatic")],
                                default="manual",
                                max_length=8,
                            ),
                        ),
                        (
                            "dota_lobby_region",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
                                max_length=32,
                            ),
                        ),
                        (
                            "discord_send_lobby_info",
                            models.BooleanField(
                                default=False,
                                help_text="DM rostered players the lobby name and password",
                            ),
                        ),
                        (
                            "dota_lobby_password",
                            models.CharField(blank=True, default="", max_length=32),
                        ),
                        (
                            "league",
                            models.ForeignKey(
                                blank=True,
                                db_column="league_fk_id",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="tournaments",
                                to="league.league",
                            ),
                        ),
                        (
                            "users",
                            models.ManyToManyField(
                                related_name="tournaments", to=settings.AUTH_USER_MODEL
                            ),
                        ),
                        (
                            "winning_team",
                            models.OneToOneField(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="tournaments_won",
                                to="tournament.team",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_tournament",
                    },
                ),
                migrations.AddField(
                    model_name="team",
                    name="tournament",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teams",
                        to="tournament.tournament",
                    ),
                ),
                migrations.CreateModel(
                    name="Game",
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
                        ("round", models.IntegerField(default=1)),
                        (
                            "bracket_type",
                            models.CharField(
                                choices=[
                                    ("winners", "Winners Bracket"),
                                    ("losers", "Losers Bracket"),
                                    ("grand_finals", "Grand Finals"),
                                    ("swiss", "Swiss"),
                                ],
                                default="winners",
                                max_length=20,
                            ),
                        ),
                        (
                            "elimination_type",
                            models.CharField(
                                choices=[
                                    ("single", "Single Elimination"),
                                    ("double", "Double Elimination"),
                                    ("swiss", "Swiss"),
                                ],
                                default="double",
                                help_text="single=loser out, double=loser drops to losers bracket, swiss=record-based",
                                max_length=10,
                            ),
                        ),
                        (
                            "position",
                            models.IntegerField(
                                default=0, help_text="Position within round (0-indexed)"
                            ),
                        ),
                        (
                            "next_game_slot",
                            models.CharField(
                                blank=True,
                                choices=[("radiant", "Radiant"), ("dire", "Dire")],
                                max_length=10,
                                null=True,
                            ),
                        ),
                        (
                            "loser_next_game_slot",
                            models.CharField(
                                blank=True,
                                choices=[("radiant", "Radiant"), ("dire", "Dire")],
                                max_length=10,
                                null=True,
                            ),
                        ),
                        (
                            "swiss_record_wins",
                            models.IntegerField(
                                default=0,
                                help_text="Team's wins entering this match (Swiss format)",
                            ),
                        ),
                        (
                            "swiss_record_losses",
                            models.IntegerField(
                                default=0,
                                help_text="Team's losses entering this match (Swiss format)",
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "Pending"),
                                    ("live", "Live"),
                                    ("completed", "Completed"),
                                ],
                                default="pending",
                                max_length=20,
                            ),
                        ),
                        ("gameid", models.BigIntegerField(blank=True, null=True)),
                        (
                            "league",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="games",
                                to="league.league",
                            ),
                        ),
                        (
                            "loser_next_game",
                            models.ForeignKey(
                                blank=True,
                                help_text="Game where loser advances to (for double elim rounds)",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="loser_source_games",
                                to="tournament.game",
                            ),
                        ),
                        (
                            "next_game",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="source_games",
                                to="tournament.game",
                            ),
                        ),
                        (
                            "dire_team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="games_as_dire",
                                to="tournament.team",
                            ),
                        ),
                        (
                            "radiant_team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="games_as_radiant",
                                to="tournament.team",
                            ),
                        ),
                        (
                            "winning_team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="games_won",
                                to="tournament.team",
                            ),
                        ),
                        (
                            "tournament",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="games",
                                to="tournament.tournament",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "app_game",
                    },
                ),
                migrations.CreateModel(
                    name="TeamLog",
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
                            "team_snapshot_id",
                            models.PositiveIntegerField(blank=True, null=True),
                        ),
                        (
                            "tournament_id",
                            models.PositiveIntegerField(blank=True, null=True),
                        ),
                        (
                            "event_id",
                            models.PositiveIntegerField(blank=True, null=True),
                        ),
                        (
                            "organization_id",
                            models.PositiveIntegerField(blank=True, null=True),
                        ),
                        ("occasion_at", models.DateTimeField(blank=True, null=True)),
                        ("team_name", models.CharField(blank=True, max_length=255)),
                        (
                            "via",
                            models.CharField(
                                choices=[
                                    ("web", "Web"),
                                    ("discord", "Discord"),
                                    ("api", "API"),
                                    ("system", "System"),
                                ],
                                max_length=16,
                            ),
                        ),
                        (
                            "action",
                            models.CharField(
                                choices=[
                                    ("set_captain", "Set Captain"),
                                    ("set_deputy", "Set Deputy"),
                                    ("mark_dropout", "Mark Dropout"),
                                    ("restore_member", "Restore Member"),
                                    ("add_standin", "Add Stand-in"),
                                    ("remove_standin", "Remove Stand-in"),
                                    ("sub_in", "Sub In"),
                                    ("rename", "Rename"),
                                    ("legacy_patch", "Legacy Patch"),
                                    ("system_succession", "System Succession"),
                                    ("empty_team_kept", "Empty Team Kept"),
                                    ("team_deleted", "Team Deleted"),
                                    ("materialize", "Materialize"),
                                ],
                                max_length=32,
                            ),
                        ),
                        ("reason", models.TextField(blank=True)),
                        ("override_rules", models.JSONField(blank=True, default=list)),
                        ("details", models.JSONField(blank=True, default=dict)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "actor",
                            models.ForeignKey(
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="team_actions_performed",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "event_team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="team_logs",
                                to="events.eventteam",
                            ),
                        ),
                        (
                            "target_user",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="team_actions_received",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "team",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="logs",
                                to="tournament.team",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Team Log",
                        "verbose_name_plural": "Team Logs",
                        "db_table": "app_teamlog",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(
                                fields=["team_snapshot_id", "-created_at"],
                                name="app_teamlog_team_sn_55b21a_idx",
                            ),
                            models.Index(
                                fields=["event_id", "-created_at"],
                                name="app_teamlog_event_i_5a0a4b_idx",
                            ),
                            models.Index(
                                fields=["tournament_id", "-created_at"],
                                name="app_teamlog_tournam_019211_idx",
                            ),
                        ],
                    },
                ),
                migrations.AddIndex(
                    model_name="tournament",
                    index=models.Index(
                        fields=["name"], name="app_tournam_name_8e0538_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="tournament",
                    index=models.Index(
                        fields=["-date_played"], name="app_tournam_date_pl_35179a_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="tournament",
                    index=models.Index(
                        fields=["state"], name="app_tournam_state_18ca9a_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="tournament",
                    index=models.Index(
                        fields=["league"], name="app_tournam_league__8406ee_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="team",
                    index=models.Index(
                        fields=["tournament"], name="app_team_tournam_97ad87_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="team",
                    index=models.Index(
                        fields=["name"], name="app_team_name_d8f293_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="team",
                    index=models.Index(
                        fields=["captain"], name="app_team_captain_5fcdd6_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="team",
                    index=models.Index(
                        fields=["deputy_captain"], name="app_team_deputy__d95afa_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["tournament"], name="app_game_tournam_ebb2c8_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["league"], name="app_game_league__9d936f_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["status"], name="app_game_status_635436_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["gameid"], name="app_game_gameid_71ac99_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["radiant_team"], name="app_game_radiant_aa1c7a_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="game",
                    index=models.Index(
                        fields=["dire_team"], name="app_game_dire_te_715044_idx"
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
