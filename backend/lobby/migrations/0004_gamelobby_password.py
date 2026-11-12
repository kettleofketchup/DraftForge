import base64
import secrets

from django.conf import settings
from django.db import migrations, models
from django.utils.crypto import salted_hmac

# The derivation lobby.passwords used before passwords were stored, inlined:
# an HMAC of `external_ref#pk` under the secret key named by password_key_id.
_SALT = "draftforge.lobby.password"
_KEY_ID_SALT = "draftforge.lobby.password.key-id"
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _key_id(secret):
    return salted_hmac(_KEY_ID_SALT, "", secret=secret, algorithm="sha256").hexdigest()[
        :16
    ]


def _derived(row, secret):
    digest = salted_hmac(
        _SALT, f"{row.external_ref}#{row.pk}", secret=secret, algorithm="sha256"
    ).digest()
    return base64.b32encode(digest).decode("ascii")[:12].lower()


def backfill_passwords(apps, schema_editor):
    """Store the password every lobby that has not ended was created with.

    A `requested` create that is retried after the upgrade must send the
    same password, or dota_lobby answers 409. A row whose key is gone could
    not be created before either; it gets its tournament's password. Ended
    lobbies keep none.
    """
    GameLobby = apps.get_model("lobby", "GameLobby")
    keys = {
        _key_id(secret): secret
        for secret in [
            settings.SECRET_KEY,
            *getattr(settings, "SECRET_KEY_FALLBACKS", []),
        ]
    }
    rows = GameLobby.objects.filter(ended=False).select_related("game__tournament")
    for row in rows.iterator():
        secret = keys.get(row.password_key_id)
        if secret is not None:
            password = _derived(row, secret)
        else:
            tournament = row.game.tournament
            password = (
                tournament.dota_lobby_password if tournament else ""
            ) or "".join(secrets.choice(ALPHABET) for _ in range(12))
        GameLobby.objects.filter(pk=row.pk).update(password=password)


class Migration(migrations.Migration):
    dependencies = [
        ("lobby", "0003_gamelobby_close_pending"),
        ("app", "0102_tournament_dota_lobby_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamelobby",
            name="password",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.RunPython(backfill_passwords, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="gamelobby",
            name="password_key_id",
        ),
    ]
