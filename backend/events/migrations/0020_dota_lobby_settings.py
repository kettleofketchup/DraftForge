import secrets

from django.db import migrations, models

# Same alphabet and length as lobby.passwords, inlined so the migration does
# not change if that module does.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
LENGTH = 12
LOBBY_FIELDS = (
    "dota_lobby_mode",
    "dota_lobby_launch",
    "dota_lobby_region",
    "discord_send_lobby_info",
)


def generate_password():
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def backfill_lobby_settings(apps, schema_editor):
    """Events take their lobby settings from the tournament they created.

    Lobby settings used to live on the tournament only. Without this the
    next event (or series) save would cascade `off` onto tournaments where
    staff had enabled lobbies. Every event gets a random password: its
    tournament's when it has one, else a new one, which the tournament then
    shares.

    A series takes its upcoming on-schedule events' settings when they all
    agree, for the same reason; otherwise it stays off and staff set it.
    """
    Event = apps.get_model("events", "Event")
    EventRepeater = apps.get_model("events", "EventRepeater")
    Tournament = apps.get_model("app", "Tournament")

    for event in Event.objects.select_related("tournament").iterator():
        tournament = event.tournament
        if tournament is not None:
            for name in LOBBY_FIELDS:
                setattr(event, name, getattr(tournament, name))
            password = tournament.dota_lobby_password or generate_password()
            if (
                tournament.dota_lobby_password != password
                and tournament.state != "past"
            ):
                Tournament.objects.filter(pk=tournament.pk).update(
                    dota_lobby_password=password
                )
        else:
            password = generate_password()
        event.dota_lobby_password_mode = "random"
        event.dota_lobby_password = password
        event.save(
            update_fields=[
                *LOBBY_FIELDS,
                "dota_lobby_password_mode",
                "dota_lobby_password",
            ]
        )

    for repeater in EventRepeater.objects.iterator():
        settings = {
            tuple(getattr(event, name) for name in LOBBY_FIELDS)
            for event in Event.objects.filter(
                event_repeater=repeater, state="upcoming", is_off_schedule=False
            )
        }
        if len(settings) == 1:
            for name, value in zip(LOBBY_FIELDS, settings.pop()):
                setattr(repeater, name, value)
            repeater.save(update_fields=list(LOBBY_FIELDS))


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0019_event_is_off_schedule"),
        ("app", "0102_tournament_dota_lobby_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="discord_send_lobby_info",
            field=models.BooleanField(
                default=False,
                help_text="DM rostered players the lobby name and password",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="dota_lobby_launch",
            field=models.CharField(
                choices=[("manual", "Manual"), ("auto", "Automatic")],
                default="manual",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="dota_lobby_mode",
            field=models.CharField(
                choices=[("off", "Off"), ("manual", "Manual"), ("auto", "Automatic")],
                default="off",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="dota_lobby_password",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="event",
            name="dota_lobby_password_mode",
            field=models.CharField(
                choices=[("fixed", "Fixed"), ("random", "Random")],
                default="random",
                help_text="fixed: staff set the lobby password; random: generated per event",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="dota_lobby_region",
            field=models.CharField(
                blank=True,
                default="",
                help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="discord_send_lobby_info",
            field=models.BooleanField(
                default=False,
                help_text="DM rostered players the lobby name and password",
            ),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="dota_lobby_launch",
            field=models.CharField(
                choices=[("manual", "Manual"), ("auto", "Automatic")],
                default="manual",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="dota_lobby_mode",
            field=models.CharField(
                choices=[("off", "Off"), ("manual", "Manual"), ("auto", "Automatic")],
                default="off",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="dota_lobby_password",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="dota_lobby_password_mode",
            field=models.CharField(
                choices=[("fixed", "Fixed"), ("random", "Random")],
                default="random",
                help_text="fixed: staff set the lobby password; random: generated per event",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="eventrepeater",
            name="dota_lobby_region",
            field=models.CharField(
                blank=True,
                default="",
                help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
                max_length=32,
            ),
        ),
        migrations.RunPython(backfill_lobby_settings, migrations.RunPython.noop),
    ]
