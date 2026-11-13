import secrets

from django.db import migrations, models

# Same alphabet and length as lobby.passwords, inlined so the migration does
# not change if that module does.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
LENGTH = 12


def generate_password():
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def backfill_passwords(apps, schema_editor):
    """Give every tournament with lobbies enabled its own random password.

    Done per row: a callable AddField default is evaluated once, so every
    row would get the same password.
    """
    Tournament = apps.get_model("app", "Tournament")
    rows = Tournament.objects.exclude(dota_lobby_mode="off").filter(
        dota_lobby_password=""
    )
    for tournament in rows.only("pk").iterator():
        Tournament.objects.filter(pk=tournament.pk).update(
            dota_lobby_password=generate_password()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0101_tournament_dota_lobby_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="dota_lobby_password",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.RunPython(backfill_passwords, migrations.RunPython.noop),
    ]
