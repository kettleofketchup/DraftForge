import importlib
import unittest

from django.conf import settings

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

lobby_0004 = importlib.import_module("lobby.migrations.0004_gamelobby_password")
ALPHABET = set("abcdefghjkmnpqrstuvwxyz23456789")


def _generated(value):
    return len(value) == 12 and set(value) <= ALPHABET


class TournamentPasswordMigrationTest(MigratorTestCase):
    """app 0102: tournaments with lobbies enabled get distinct passwords."""

    migrate_from = ("app", "0101_tournament_dota_lobby_fields")
    migrate_to = ("app", "0102_tournament_dota_lobby_password")

    def prepare(self):
        Tournament = self.old_state.apps.get_model("app", "Tournament")
        date = "2026-11-20T18:00:00Z"
        self.on = Tournament.objects.create(
            name="On", date_played=date, dota_lobby_mode="auto"
        ).pk
        self.on_too = Tournament.objects.create(
            name="On too", date_played=date, dota_lobby_mode="manual"
        ).pk
        self.off = Tournament.objects.create(name="Off", date_played=date).pk

    def test_passwords(self):
        Tournament = self.new_state.apps.get_model("app", "Tournament")
        on = Tournament.objects.get(pk=self.on).dota_lobby_password
        on_too = Tournament.objects.get(pk=self.on_too).dota_lobby_password
        self.assertTrue(_generated(on))
        self.assertTrue(_generated(on_too))
        self.assertNotEqual(on, on_too)
        self.assertEqual(Tournament.objects.get(pk=self.off).dota_lobby_password, "")


class EventLobbySettingsMigrationTest(MigratorTestCase):
    """events 0020: events take their tournament's lobby settings."""

    # app 0102 first: the plan is truncated at the latest target, and events
    # 0020 depends on it.
    migrate_from = [
        ("app", "0102_tournament_dota_lobby_password"),
        ("events", "0019_event_is_off_schedule"),
    ]
    migrate_to = ("events", "0020_dota_lobby_settings")

    def prepare(self):
        apps = self.old_state.apps
        Tournament = apps.get_model("app", "Tournament")
        Organization = apps.get_model("app", "Organization")
        Event = apps.get_model("events", "Event")
        EventRepeater = apps.get_model("events", "EventRepeater")

        date = "2026-11-20T18:00:00Z"
        on = Tournament.objects.create(
            name="On",
            date_played=date,
            dota_lobby_mode="auto",
            dota_lobby_region="europe",
            discord_send_lobby_info=True,
        )
        no_password = Tournament.objects.create(
            name="On, no password", date_played=date, dota_lobby_mode="manual"
        )
        Tournament.objects.filter(pk=on.pk).update(dota_lobby_password="kept-pw")
        Tournament.objects.filter(pk=no_password.pk).update(dota_lobby_password="")
        org = Organization.objects.create(name="Migration Org")
        agreeing = EventRepeater.objects.create(
            organization=org,
            name="Agreeing",
            frequency="weekly",
            day_of_week=1,
            time_of_day="20:00",
            starts_at="2026-11-01",
        )
        mixed = EventRepeater.objects.create(
            organization=org,
            name="Mixed",
            frequency="weekly",
            day_of_week=2,
            time_of_day="20:00",
            starts_at="2026-11-01",
        )

        def event(name, **fields):
            return Event.objects.create(
                organization=org, name=name, scheduled_at=date, **fields
            ).pk

        self.pks = {
            "on": on.pk,
            "no_password": no_password.pk,
            "agreeing": agreeing.pk,
            "mixed": mixed.pk,
            "with_tournament": event(
                "With", event_repeater=agreeing, state="upcoming", tournament=on
            ),
            "without": event("Without"),
        }
        self.pks["no_password_event"] = Event.objects.create(
            organization=org,
            name="No password",
            scheduled_at="2026-11-21T18:00:00Z",
            event_repeater=mixed,
            state="upcoming",
            tournament=no_password,
        ).pk
        Event.objects.create(
            organization=org,
            name="Mixed, no tournament",
            scheduled_at="2026-11-22T18:00:00Z",
            event_repeater=mixed,
            state="upcoming",
        )

    def test_events_take_their_tournament_settings(self):
        apps = self.new_state.apps
        Event = apps.get_model("events", "Event")
        Tournament = apps.get_model("app", "Tournament")
        event = Event.objects.get(pk=self.pks["with_tournament"])
        self.assertEqual(event.dota_lobby_mode, "auto")
        self.assertEqual(event.dota_lobby_region, "europe")
        self.assertTrue(event.discord_send_lobby_info)
        self.assertEqual(event.dota_lobby_password_mode, "random")
        self.assertEqual(event.dota_lobby_password, "kept-pw")

        healed = Event.objects.get(pk=self.pks["no_password_event"])
        self.assertTrue(_generated(healed.dota_lobby_password))
        self.assertEqual(
            Tournament.objects.get(pk=self.pks["no_password"]).dota_lobby_password,
            healed.dota_lobby_password,
        )

        without = Event.objects.get(pk=self.pks["without"])
        self.assertEqual(without.dota_lobby_mode, "off")
        self.assertTrue(_generated(without.dota_lobby_password))

    def test_series_take_agreeing_upcoming_event_settings(self):
        EventRepeater = self.new_state.apps.get_model("events", "EventRepeater")
        agreeing = EventRepeater.objects.get(pk=self.pks["agreeing"])
        self.assertEqual(agreeing.dota_lobby_mode, "auto")
        self.assertEqual(agreeing.dota_lobby_region, "europe")
        self.assertEqual(agreeing.dota_lobby_password_mode, "random")
        self.assertEqual(agreeing.dota_lobby_password, "")
        mixed = EventRepeater.objects.get(pk=self.pks["mixed"])
        self.assertEqual(mixed.dota_lobby_mode, "off")


class GameLobbyPasswordMigrationTest(MigratorTestCase):
    """lobby 0004: lobbies keep the password they were created with."""

    migrate_from = [
        ("app", "0102_tournament_dota_lobby_password"),
        ("lobby", "0003_gamelobby_close_pending"),
    ]
    migrate_to = ("lobby", "0004_gamelobby_password")

    def prepare(self):
        apps = self.old_state.apps
        Tournament = apps.get_model("app", "Tournament")
        Game = apps.get_model("app", "Game")
        GameLobby = apps.get_model("lobby", "GameLobby")

        tournament = Tournament.objects.create(
            name="On", date_played="2026-11-20T18:00:00Z", dota_lobby_mode="auto"
        )
        Tournament.objects.filter(pk=tournament.pk).update(
            dota_lobby_password="tournament-pw"
        )
        game = Game.objects.create(tournament=tournament)
        other_game = Game.objects.create(tournament=tournament)
        current_key = lobby_0004._key_id(settings.SECRET_KEY)
        derived = GameLobby.objects.create(
            game=game, external_ref=f"game:{game.pk}", password_key_id=current_key
        )
        ended = GameLobby.objects.create(
            game=game,
            external_ref=f"game:{game.pk}",
            state="closed",
            ended=True,
            password_key_id=current_key,
        )
        key_gone = GameLobby.objects.create(
            game=other_game,
            external_ref=f"game:{other_game.pk}",
            password_key_id="0123456789abcdef",
        )
        self.pks = {"derived": derived.pk, "ended": ended.pk, "key_gone": key_gone.pk}
        self.expected_derived = lobby_0004._derived(derived, settings.SECRET_KEY)

    def test_passwords(self):
        GameLobby = self.new_state.apps.get_model("lobby", "GameLobby")
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["derived"]).password,
            self.expected_derived,
        )
        self.assertEqual(GameLobby.objects.get(pk=self.pks["ended"]).password, "")
        self.assertEqual(
            GameLobby.objects.get(pk=self.pks["key_gone"]).password, "tournament-pw"
        )
        self.assertNotIn(
            "password_key_id", {f.name for f in GameLobby._meta.get_fields()}
        )
