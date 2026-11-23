import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("draft", "0005_herodraft_chat_withdraw_suggestion"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="draft",
                    name="tournament",
                    field=models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="draft",
                        to="tournament.tournament",
                    ),
                ),
                migrations.AlterField(
                    model_name="draftoptions",
                    name="tournament",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="draft_options",
                        to="tournament.tournament",
                    ),
                ),
                migrations.AlterField(
                    model_name="draftteam",
                    name="tournament_team",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hero_draft_teams",
                        to="tournament.team",
                    ),
                ),
                migrations.AlterField(
                    model_name="herodraft",
                    name="game",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="herodraft",
                        to="tournament.game",
                    ),
                ),
                migrations.AlterField(
                    model_name="herodraftchatmembership",
                    name="team",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="tournament.team",
                    ),
                ),
                migrations.AlterField(
                    model_name="herodraftchatmessage",
                    name="team",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="tournament.team",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
