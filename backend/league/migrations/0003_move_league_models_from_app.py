import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0111_move_organization_models_to_org"),
        ("league", "0002_populate_league_users"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="League",
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
                            "steam_league_id",
                            models.IntegerField(blank=True, null=True, unique=True),
                        ),
                        ("name", models.CharField(max_length=255)),
                        (
                            "description",
                            models.TextField(blank=True, default="", max_length=10000),
                        ),
                        (
                            "rules",
                            models.TextField(blank=True, default="", max_length=50000),
                        ),
                        (
                            "prize_pool",
                            models.CharField(blank=True, default="", max_length=100),
                        ),
                        (
                            "timezone",
                            models.CharField(default="America/New_York", max_length=50),
                        ),
                        ("last_synced", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "rating_system",
                            models.CharField(
                                choices=[
                                    ("elo", "Elo"),
                                    ("fixed_delta", "Fixed Delta"),
                                ],
                                default="elo",
                                help_text="Rating calculation method",
                                max_length=20,
                            ),
                        ),
                        (
                            "k_factor_default",
                            models.FloatField(
                                default=32.0,
                                help_text="Default K-factor for Elo calculations",
                            ),
                        ),
                        (
                            "k_factor_placement",
                            models.FloatField(
                                default=64.0,
                                help_text="K-factor for players in placement games",
                            ),
                        ),
                        (
                            "placement_games",
                            models.PositiveIntegerField(
                                default=10,
                                help_text="Number of placement games before using default K-factor",
                            ),
                        ),
                        (
                            "fixed_delta",
                            models.FloatField(
                                default=25.0,
                                help_text="Fixed rating change per game (for fixed_delta system)",
                            ),
                        ),
                        (
                            "age_decay_enabled",
                            models.BooleanField(
                                default=False,
                                help_text="Enable age-based decay for older matches",
                            ),
                        ),
                        (
                            "age_decay_half_life_days",
                            models.PositiveIntegerField(
                                default=180,
                                help_text="Half-life in days for age decay calculation",
                            ),
                        ),
                        (
                            "age_decay_minimum",
                            models.FloatField(
                                default=0.1, help_text="Minimum decay factor (0.0-1.0)"
                            ),
                        ),
                        (
                            "recalc_max_age_days",
                            models.PositiveIntegerField(
                                default=90,
                                help_text="Maximum age in days for match recalculation",
                            ),
                        ),
                        (
                            "recalc_mmr_threshold",
                            models.PositiveIntegerField(
                                default=500,
                                help_text="Maximum MMR change allowed for recalculation",
                            ),
                        ),
                        (
                            "admins",
                            models.ManyToManyField(
                                blank=True,
                                related_name="admin_leagues",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "organization",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="leagues",
                                to="org.organization",
                            ),
                        ),
                        (
                            "staff",
                            models.ManyToManyField(
                                blank=True,
                                related_name="staff_leagues",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "League",
                        "verbose_name_plural": "Leagues",
                        "db_table": "app_league",
                        "indexes": [
                            models.Index(
                                fields=["name"], name="app_league_name_844732_idx"
                            ),
                            models.Index(
                                fields=["created_at"],
                                name="app_league_created_a10ab0_idx",
                            ),
                        ],
                        "ordering": ["name"],
                    },
                ),
                migrations.CreateModel(
                    name="LeagueLog",
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
                                    ("link_organization", "Link Organization"),
                                    ("unlink_organization", "Unlink Organization"),
                                    ("create", "Create League"),
                                    ("update", "Update League"),
                                    ("delete", "Delete League"),
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
                                related_name="league_actions_performed",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "league",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="logs",
                                to="league.league",
                            ),
                        ),
                        (
                            "target_user",
                            models.ForeignKey(
                                blank=True,
                                help_text="User affected by the action (if applicable)",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="league_actions_received",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "League Log",
                        "verbose_name_plural": "League Logs",
                        "db_table": "app_leaguelog",
                        "indexes": [
                            models.Index(
                                fields=["league", "-created_at"],
                                name="app_leaguel_league__800628_idx",
                            )
                        ],
                        "ordering": ["-created_at"],
                    },
                ),
                migrations.CreateModel(
                    name="LeagueRating",
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
                            "base_mmr",
                            models.IntegerField(
                                default=0,
                                help_text="Player's MMR when joining the league",
                            ),
                        ),
                        (
                            "positive_stats",
                            models.FloatField(
                                default=0.0,
                                help_text="Accumulated positive rating changes (wins)",
                            ),
                        ),
                        (
                            "negative_stats",
                            models.FloatField(
                                default=0.0,
                                help_text="Accumulated negative rating changes (losses)",
                            ),
                        ),
                        (
                            "rating_deviation",
                            models.FloatField(
                                default=350.0,
                                help_text="Rating deviation (uncertainty) for Glicko-2",
                            ),
                        ),
                        (
                            "volatility",
                            models.FloatField(
                                default=0.06, help_text="Volatility for Glicko-2"
                            ),
                        ),
                        ("games_played", models.PositiveIntegerField(default=0)),
                        ("wins", models.PositiveIntegerField(default=0)),
                        ("losses", models.PositiveIntegerField(default=0)),
                        ("last_played", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "league",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="ratings",
                                to="league.league",
                            ),
                        ),
                        (
                            "player",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="league_ratings",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "League Rating",
                        "verbose_name_plural": "League Ratings",
                        "db_table": "app_leaguerating",
                        "unique_together": {("league", "player")},
                        "ordering": ["-positive_stats", "negative_stats"],
                    },
                ),
                migrations.CreateModel(
                    name="LeagueMatch",
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
                            "played_at",
                            models.DateTimeField(help_text="When the match was played"),
                        ),
                        (
                            "stage",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Tournament stage (e.g., 'quarterfinal', 'grand_final')",
                                max_length=64,
                            ),
                        ),
                        (
                            "bracket_slot",
                            models.CharField(
                                blank=True,
                                help_text="Bracket position identifier",
                                max_length=32,
                                null=True,
                            ),
                        ),
                        (
                            "is_finalized",
                            models.BooleanField(
                                default=False,
                                help_text="Whether ratings have been calculated",
                            ),
                        ),
                        (
                            "finalized_at",
                            models.DateTimeField(
                                blank=True,
                                help_text="When ratings were calculated",
                                null=True,
                            ),
                        ),
                        (
                            "recalculation_count",
                            models.PositiveIntegerField(
                                default=0,
                                help_text="Number of times this match has been recalculated",
                            ),
                        ),
                        (
                            "last_recalculated_at",
                            models.DateTimeField(
                                blank=True,
                                help_text="When ratings were last recalculated",
                                null=True,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "game",
                            models.OneToOneField(
                                blank=True,
                                help_text="Link to Game model if applicable",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="league_match",
                                to="app.game",
                            ),
                        ),
                        (
                            "league",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="matches",
                                to="league.league",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "League Match",
                        "verbose_name_plural": "League Matches",
                        "db_table": "app_leaguematch",
                        "ordering": ["-played_at"],
                    },
                ),
                migrations.CreateModel(
                    name="LeagueMatchParticipant",
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
                            "team_side",
                            models.CharField(
                                choices=[("radiant", "Radiant"), ("dire", "Dire")],
                                max_length=8,
                            ),
                        ),
                        (
                            "mmr_at_match",
                            models.IntegerField(
                                help_text="Player's base MMR at time of match"
                            ),
                        ),
                        (
                            "elo_before",
                            models.FloatField(
                                help_text="Player's total Elo before this match"
                            ),
                        ),
                        (
                            "elo_after",
                            models.FloatField(
                                help_text="Player's total Elo after this match"
                            ),
                        ),
                        (
                            "k_factor_used",
                            models.FloatField(help_text="K-factor used in calculation"),
                        ),
                        (
                            "rating_deviation_used",
                            models.FloatField(
                                default=350.0,
                                help_text="Rating deviation at time of calculation",
                            ),
                        ),
                        (
                            "age_decay_factor",
                            models.FloatField(
                                default=1.0,
                                help_text="Age decay factor applied (1.0 = no decay)",
                            ),
                        ),
                        ("is_winner", models.BooleanField()),
                        (
                            "delta",
                            models.FloatField(
                                help_text="Rating change from this match"
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "match",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="participants",
                                to="league.leaguematch",
                            ),
                        ),
                        (
                            "player",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="league_match_participations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "player_rating",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="match_participations",
                                to="league.leaguerating",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "League Match Participant",
                        "verbose_name_plural": "League Match Participants",
                        "db_table": "app_leaguematchparticipant",
                        "unique_together": {("match", "player")},
                        "ordering": ["team_side", "player__username"],
                    },
                ),
                migrations.AlterField(
                    model_name="leagueuser",
                    name="league",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="league.league",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
