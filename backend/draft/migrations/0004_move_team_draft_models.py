import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("draft", "0003_backfill_herodraft_chat_memberships"),
        ("app", "0108_move_hero_draft_models_to_draft"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Draft',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('draft_style', models.CharField(choices=[('snake', 'Snake'), ('normal', 'Normal'), ('shuffle', 'Shuffle')], default='snake', help_text='Draft style: snake, normal, or shuffle', max_length=10)),
                        ('state', models.CharField(choices=[('pending', 'Pending'), ('drafting', 'Drafting'), ('paused', 'Paused'), ('resuming', 'Resuming'), ('completed', 'Completed')], default='pending', max_length=16)),
                        ('paused_at', models.DateTimeField(blank=True, null=True)),
                        ('resuming_until', models.DateTimeField(blank=True, null=True)),
                        ('is_manual_pause', models.BooleanField(default=False)),
                        ('tournament', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='draft', to='app.tournament')),
                    ],
                    options={
                        'db_table': 'app_draft',
                    },
                ),
                migrations.CreateModel(
                    name='DraftOptions',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('timer_enabled', models.BooleanField(default=True)),
                        ('grace_time_ms', models.IntegerField(default=30000)),
                        ('reserve_time_ms', models.IntegerField(default=30000)),
                        ('timeout_action', models.CharField(choices=[('skip_turn', 'Skip turn')], default='skip_turn', max_length=32)),
                        ('hero_timer_enabled', models.BooleanField(default=True)),
                        ('hero_grace_time_ms', models.IntegerField(default=30000)),
                        ('hero_reserve_time_ms', models.IntegerField(default=90000)),
                        ('tournament', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='draft_options', to='app.tournament')),
                    ],
                    options={
                        'db_table': 'app_draftoptions',
                    },
                ),
                migrations.CreateModel(
                    name='DraftRound',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('pick_number', models.IntegerField(blank=True, default=1, help_text='pick number starts at 1, and counts all picks')),
                        ('pick_phase', models.IntegerField(blank=True, default=1, help_text='pick phase is only increase after all captains have picked once')),
                        ('was_tie', models.BooleanField(default=False, help_text='Whether this round was determined by a tie-breaker roll')),
                        ('tie_roll_data', models.JSONField(blank=True, help_text='Stores tie resolution: {tied_teams, roll_rounds, winner_id}', null=True)),
                        ('started_at', models.DateTimeField(blank=True, null=True)),
                        ('completed_at', models.DateTimeField(blank=True, null=True)),
                        ('timed_out_at', models.DateTimeField(blank=True, null=True)),
                        ('grace_time_ms', models.IntegerField(blank=True, null=True)),
                        ('pick_duration_ms', models.IntegerField(blank=True, null=True)),
                        ('reserve_used_ms', models.IntegerField(blank=True, null=True)),
                        ('skip_count', models.IntegerField(default=0)),
                        ('captain', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='draft_rounds_captained', to=settings.AUTH_USER_MODEL)),
                        ('choice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='draftrounds_choice', to=settings.AUTH_USER_MODEL)),
                        ('draft', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='draft_rounds', to='draft.draft')),
                    ],
                    options={
                        'db_table': 'app_draftround',
                        'ordering': ['pick_number'],
                    },
                ),
                migrations.CreateModel(
                    name='DraftEvent',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('event_type', models.CharField(choices=[('draft_started', 'Draft Started'), ('draft_completed', 'Draft Completed'), ('captain_assigned', 'Captain Assigned'), ('player_picked', 'Player Picked'), ('tie_roll', 'Tie Roll'), ('pick_undone', 'Pick Undone'), ('draft_lobby_opened', 'Draft Lobby Opened'), ('captain_ready', 'Captain Ready'), ('captain_unready', 'Captain Unready'), ('captain_connected', 'Captain Connected'), ('captain_disconnected', 'Captain Disconnected'), ('draft_started_by_staff', 'Draft Started By Staff'), ('draft_force_started', 'Draft Force Started'), ('round_started', 'Round Started'), ('draft_paused', 'Draft Paused'), ('draft_resumed', 'Draft Resumed'), ('pick_timed_out', 'Pick Timed Out'), ('pick_skipped', 'Pick Skipped'), ('pick_skip_unavailable', 'Pick Skip Unavailable'), ('draft_options_changed', 'Draft Options Changed'), ('team_changed', 'Team Changed')], max_length=32)),
                        ('payload', models.JSONField(default=dict, help_text='Event-specific data (JSON)')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('actor', models.ForeignKey(blank=True, help_text='User who triggered this event', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='draft_events_triggered', to=settings.AUTH_USER_MODEL)),
                        ('draft', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='draft.draft')),
                    ],
                    options={
                        'db_table': 'app_draftevent',
                        'ordering': ['-created_at'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
