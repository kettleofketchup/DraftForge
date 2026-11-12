"""Event lobby passwords: series -> event -> tournament cascade, visibility."""

from datetime import time, timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, DotaLobbyMode, GameMode, Team, Tournament
from events.constants import EventState, RepeatFrequency, SignupStatus
from events.models import Event, EventRepeater, EventSignup
from events.serializers import EventSerializer
from events.services import (
    create_off_schedule_event,
    create_tournament_for_event,
    generate_events_for_repeater,
    is_registered_for_event,
    regenerate_event_lobby_password,
    sync_future_events,
)
from events.tests.base import EventTestCase
from lobby.passwords import ALPHABET, GENERATED_LENGTH, PasswordMode

FIXED = PasswordMode.FIXED
RANDOM = PasswordMode.RANDOM


def _is_generated(password: str) -> bool:
    return len(password) == GENERATED_LENGTH and set(password) <= set(ALPHABET)


@patch("events.services.notify_create_discord_event")
@patch("events.services.notify_new_event")
class SeriesCascadeTests(EventTestCase):
    def make_repeater(self, **fields):
        defaults = dict(
            organization=self.org,
            name="Thursday Inhouse",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=1),
            generate_days_ahead=2,
            created_by=self.admin,
            dota_lobby_mode=DotaLobbyMode.AUTO,
            dota_lobby_launch="auto",
            dota_lobby_region="europe",
            discord_send_lobby_info=True,
        )
        defaults.update(fields)
        return EventRepeater.objects.create(**defaults)

    def test_fixed_series_password_reaches_events_and_tournaments(self, *_):
        repeater = self.make_repeater(
            dota_lobby_password_mode=FIXED, dota_lobby_password="night-4"
        )
        events = generate_events_for_repeater(repeater)
        self.assertEqual(len(events), 2)
        for event in events:
            event.refresh_from_db()
            self.assertEqual(event.dota_lobby_password_mode, FIXED)
            self.assertEqual(event.dota_lobby_password, "night-4")
            tournament = event.tournament
            self.assertEqual(tournament.dota_lobby_password, "night-4")
            self.assertEqual(tournament.dota_lobby_mode, DotaLobbyMode.AUTO)
            self.assertEqual(tournament.dota_lobby_launch, "auto")
            self.assertEqual(tournament.dota_lobby_region, "europe")
            self.assertTrue(tournament.discord_send_lobby_info)

    def test_random_series_generates_one_password_per_event(self, *_):
        repeater = self.make_repeater()
        events = generate_events_for_repeater(repeater)
        passwords = [e.dota_lobby_password for e in events]
        self.assertTrue(all(_is_generated(p) for p in passwords))
        self.assertEqual(len(set(passwords)), len(passwords))
        self.assertEqual(repeater.dota_lobby_password, "")
        for event in events:
            self.assertEqual(
                event.tournament.dota_lobby_password, event.dota_lobby_password
            )

    def test_series_save_keeps_random_passwords(self, *_):
        repeater = self.make_repeater()
        events = generate_events_for_repeater(repeater)
        before = {e.pk: e.dota_lobby_password for e in events}
        repeater.dota_lobby_region = "us_east"
        repeater.save()
        sync_future_events(repeater)
        for event in Event.objects.filter(pk__in=before):
            self.assertEqual(event.dota_lobby_password, before[event.pk])
            self.assertEqual(event.dota_lobby_region, "us_east")
            self.assertEqual(event.tournament.dota_lobby_region, "us_east")

    def test_switching_series_to_fixed_then_random(self, *_):
        repeater = self.make_repeater()
        events = generate_events_for_repeater(repeater)
        repeater.dota_lobby_password_mode = FIXED
        repeater.dota_lobby_password = "shared-pw"
        repeater.save()
        sync_future_events(repeater)
        for event in Event.objects.filter(pk__in=[e.pk for e in events]):
            self.assertEqual(event.dota_lobby_password, "shared-pw")
            self.assertEqual(event.tournament.dota_lobby_password, "shared-pw")

        repeater.dota_lobby_password_mode = RANDOM
        repeater.dota_lobby_password = ""
        repeater.save()
        sync_future_events(repeater)
        passwords = set()
        for event in Event.objects.filter(pk__in=[e.pk for e in events]):
            self.assertEqual(event.dota_lobby_password_mode, RANDOM)
            self.assertTrue(_is_generated(event.dota_lobby_password))
            self.assertEqual(
                event.tournament.dota_lobby_password, event.dota_lobby_password
            )
            passwords.add(event.dota_lobby_password)
        self.assertEqual(len(passwords), len(events))

    def test_cascade_skips_off_schedule_and_started_events(self, *_):
        repeater = self.make_repeater(
            dota_lobby_password_mode=FIXED, dota_lobby_password="first"
        )
        one_off = create_off_schedule_event(
            repeater,
            scheduled_at=tz.now() + timedelta(days=30, hours=1),
            created_by=self.admin,
        )
        started = generate_events_for_repeater(repeater)[0]
        started.state = EventState.SIGNUPS_OPEN
        started.save()

        repeater.dota_lobby_password = "second"
        repeater.dota_lobby_mode = DotaLobbyMode.MANUAL
        repeater.save()
        touched = sync_future_events(repeater)

        self.assertNotIn(one_off.pk, {e.pk for e in touched})
        self.assertNotIn(started.pk, {e.pk for e in touched})
        for event in (one_off, started):
            event.refresh_from_db()
            self.assertEqual(event.dota_lobby_password, "first")
            self.assertEqual(event.dota_lobby_mode, DotaLobbyMode.AUTO)
            self.assertEqual(event.tournament.dota_lobby_password, "first")
        self.assertTrue(touched)
        for event in touched:
            self.assertEqual(event.dota_lobby_password, "second")

    def test_event_override_lasts_until_the_next_series_save(self, *_):
        repeater = self.make_repeater(
            dota_lobby_password_mode=FIXED, dota_lobby_password="series-pw"
        )
        event = generate_events_for_repeater(repeater)[0]
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.patch(
            f"/api/events/{event.pk}/",
            {"dota_lobby_password": "event-pw"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        event.refresh_from_db()
        self.assertEqual(event.dota_lobby_password, "event-pw")
        self.assertEqual(event.tournament.dota_lobby_password, "event-pw")

        sync_future_events(repeater)
        event.refresh_from_db()
        self.assertEqual(event.dota_lobby_password, "series-pw")

    def test_off_schedule_overrides(self, *_):
        repeater = self.make_repeater(
            dota_lobby_password_mode=FIXED, dota_lobby_password="series-pw"
        )
        when = tz.now() + timedelta(days=40, hours=3)
        inherited = create_off_schedule_event(
            repeater, scheduled_at=when, created_by=self.admin
        )
        self.assertEqual(inherited.dota_lobby_password, "series-pw")

        overridden = create_off_schedule_event(
            repeater,
            scheduled_at=when + timedelta(hours=1),
            created_by=self.admin,
            overrides={"dota_lobby_password": "special"},
        )
        self.assertEqual(overridden.dota_lobby_password, "special")
        self.assertEqual(overridden.tournament.dota_lobby_password, "special")

        random = create_off_schedule_event(
            repeater,
            scheduled_at=when + timedelta(hours=2),
            created_by=self.admin,
            overrides={"dota_lobby_password_mode": RANDOM},
        )
        self.assertTrue(_is_generated(random.dota_lobby_password))

    def test_one_off_endpoint_validates_the_password(self, *_):
        repeater = self.make_repeater()
        client = APIClient()
        client.force_authenticate(self.admin)
        url = f"/api/events/repeaters/{repeater.pk}/create-event/"
        when = (tz.now() + timedelta(days=50, hours=5)).isoformat()
        resp = client.post(
            url,
            {"scheduled_at": when, "dota_lobby_password_mode": FIXED},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("dota_lobby_password", resp.data)

        resp = client.post(
            url,
            {
                "scheduled_at": when,
                "dota_lobby_password_mode": FIXED,
                "dota_lobby_password": "one-off-pw",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertNotIn("dota_lobby_password", resp.data)
        event = Event.objects.get(pk=resp.data["id"])
        self.assertEqual(event.dota_lobby_password, "one-off-pw")


class TournamentCopyTests(EventTestCase):
    def test_create_tournament_copies_lobby_settings_and_password(self):
        event = Event.objects.create(
            organization=self.org,
            name="Single",
            scheduled_at=tz.now() + timedelta(days=3),
            dota_lobby_mode=DotaLobbyMode.MANUAL,
            dota_lobby_region="sea",
            dota_lobby_password_mode=FIXED,
            dota_lobby_password="copy-me",
        )
        tournament = create_tournament_for_event(event)
        self.assertEqual(tournament.dota_lobby_mode, DotaLobbyMode.MANUAL)
        self.assertEqual(tournament.dota_lobby_region, "sea")
        self.assertEqual(tournament.dota_lobby_password, "copy-me")

    def test_new_random_event_gets_a_password(self):
        event = Event.objects.create(
            organization=self.org,
            name="Random",
            scheduled_at=tz.now() + timedelta(days=3),
        )
        self.assertEqual(event.dota_lobby_password_mode, RANDOM)
        self.assertTrue(_is_generated(event.dota_lobby_password))

    def test_standalone_tournament_gets_a_password_when_lobbies_are_on(self):
        off = Tournament.objects.create(name="Off", date_played=tz.now())
        self.assertEqual(off.dota_lobby_password, "")
        on = Tournament.objects.create(
            name="On", date_played=tz.now(), dota_lobby_mode=DotaLobbyMode.MANUAL
        )
        self.assertTrue(_is_generated(on.dota_lobby_password))
        off.dota_lobby_mode = DotaLobbyMode.AUTO
        off.save(update_fields=["dota_lobby_mode"])
        off.refresh_from_db()
        self.assertTrue(_is_generated(off.dota_lobby_password))


class EventPasswordApiTestCase(EventTestCase):
    def setUp(self):
        self.event = Event.objects.create(
            organization=self.org,
            name="Lobby Night",
            scheduled_at=tz.now() + timedelta(days=5),
            state=EventState.SIGNUPS_OPEN,
            tournament_league=self.league,
            dota_lobby_mode=DotaLobbyMode.MANUAL,
        )
        self.tournament = create_tournament_for_event(self.event)
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def url(self, suffix=""):
        return f"/api/events/{self.event.pk}/lobby-password/{suffix}"

    def make_user(self, name):
        return CustomUser.objects.create_user(username=name, password="x")


class EventPasswordEditTests(EventPasswordApiTestCase):
    def patch(self, data):
        return self.as_user(self.admin).patch(
            f"/api/events/{self.event.pk}/", data, format="json"
        )

    def test_fixed_password_is_validated(self):
        for bad in ("", " padded", "padded ", "x" * 33, "naïve"):
            with self.subTest(password=bad):
                resp = self.patch(
                    {"dota_lobby_password_mode": FIXED, "dota_lobby_password": bad}
                )
                self.assertEqual(resp.status_code, 400)
                self.assertIn("dota_lobby_password", resp.data)
        resp = self.patch({"dota_lobby_password_mode": FIXED})
        self.assertEqual(resp.status_code, 400)

    def test_fixed_password_saved_and_copied_never_returned(self):
        resp = self.patch(
            {"dota_lobby_password_mode": FIXED, "dota_lobby_password": "Team Night!"}
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertNotIn("dota_lobby_password", resp.data)
        self.assertNotIn("Team Night!", str(resp.content))
        self.event.refresh_from_db()
        self.tournament.refresh_from_db()
        self.assertEqual(self.event.dota_lobby_password, "Team Night!")
        self.assertEqual(self.tournament.dota_lobby_password, "Team Night!")

        # An unrelated PATCH keeps the fixed password.
        self.assertEqual(self.patch({"name": "Renamed"}).status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.dota_lobby_password, "Team Night!")

    def test_random_keeps_its_password_until_switched_from_fixed(self):
        original = self.event.dota_lobby_password
        self.assertEqual(
            self.patch({"dota_lobby_password_mode": RANDOM}).status_code, 200
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.dota_lobby_password, original)

        self.patch({"dota_lobby_password_mode": FIXED, "dota_lobby_password": "fx"})
        self.patch(
            {"dota_lobby_password_mode": RANDOM, "dota_lobby_password": "ignored"}
        )
        self.event.refresh_from_db()
        self.assertTrue(_is_generated(self.event.dota_lobby_password))
        self.assertNotIn(self.event.dota_lobby_password, (original, "fx", "ignored"))

    def test_in_progress_tournament_gets_the_new_password(self):
        self.tournament.state = "in_progress"
        self.tournament.save()
        resp = self.patch(
            {"dota_lobby_password_mode": FIXED, "dota_lobby_password": "mid-event"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("lobby password", resp.data["_warning"])
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.dota_lobby_password, "mid-event")

    def test_past_tournament_keeps_its_password(self):
        self.tournament.state = "past"
        self.tournament.save()
        before = self.tournament.dota_lobby_password
        self.patch({"dota_lobby_password_mode": FIXED, "dota_lobby_password": "late"})
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.dota_lobby_password, before)

    def test_league_staff_cannot_edit(self):
        resp = self.as_user(self.league_staff).patch(
            f"/api/events/{self.event.pk}/",
            {"dota_lobby_password_mode": FIXED, "dota_lobby_password": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class RegeneratePasswordTests(EventPasswordApiTestCase):
    def test_staff_regenerates_random_password(self):
        before = self.event.dota_lobby_password
        resp = self.as_user(self.admin).post(self.url("regenerate/"))
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.tournament.refresh_from_db()
        self.assertNotEqual(self.event.dota_lobby_password, before)
        self.assertEqual(resp.data["password"], self.event.dota_lobby_password)
        self.assertEqual(resp.data["source"], "event")
        self.assertEqual(
            self.tournament.dota_lobby_password, self.event.dota_lobby_password
        )

    def test_regenerate_reports_the_series_source(self):
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=3,
            time_of_day=time(19, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        Event.objects.filter(pk=self.event.pk).update(event_repeater=repeater)
        resp = self.as_user(self.admin).post(self.url("regenerate/"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["source"], "series")

    def test_fixed_password_cannot_be_regenerated(self):
        self.event.dota_lobby_password_mode = FIXED
        self.event.dota_lobby_password = "fixed"
        self.event.save()
        resp = self.as_user(self.admin).post(self.url("regenerate/"))
        self.assertEqual(resp.status_code, 409)
        with self.assertRaises(ValueError):
            regenerate_event_lobby_password(self.event)

    def test_others_cannot_regenerate(self):
        for user in (self.league_staff, self.unrelated_user):
            with self.subTest(user=user.username):
                resp = self.as_user(user).post(self.url("regenerate/"))
                self.assertEqual(resp.status_code, 404)
        self.assertIn(APIClient().post(self.url("regenerate/")).status_code, (401, 403))

    def test_existing_lobbies_keep_their_password(self):
        from lobby.models import GameLobby

        game = self.tournament.games.create(round=1)
        lobby = GameLobby.objects.create(
            game=game,
            external_ref=f"game:{game.pk}",
            password=self.tournament.dota_lobby_password,
        )
        old = lobby.password
        self.as_user(self.admin).post(self.url("regenerate/"))
        lobby.refresh_from_db()
        self.assertEqual(lobby.password, old)


class PasswordVisibilityTests(EventPasswordApiTestCase):
    def signed_up(self, status):
        user = self.make_user(f"player_{status}")
        EventSignup.objects.create(event=self.event, user=user, status=status)
        return user

    def test_staff_sees_mode_and_password(self):
        resp = self.as_user(self.admin).get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["password"], self.event.dota_lobby_password)
        self.assertEqual(resp.data["mode"], RANDOM)
        self.assertEqual(resp.data["source"], "event")
        self.assertTrue(resp.data["can_manage"])

    def attach_to_series(self, *, series_mode, series_password="", **event_fields):
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=3,
            time_of_day=time(19, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
            dota_lobby_password_mode=series_mode,
            dota_lobby_password=series_password,
        )
        # update(): no save side effects; only the fields under test change.
        Event.objects.filter(pk=self.event.pk).update(
            event_repeater=repeater, **event_fields
        )
        return repeater

    def source(self):
        resp = self.as_user(self.admin).get(self.url())
        self.assertEqual(resp.status_code, 200)
        return resp.data["source"]

    def test_source_on_schedule_random_event_of_a_random_series(self):
        self.attach_to_series(series_mode=RANDOM)
        self.assertEqual(self.source(), "series")

    def test_source_fixed_event_with_the_series_password(self):
        self.attach_to_series(
            series_mode=FIXED,
            series_password="night-4",
            dota_lobby_password_mode=FIXED,
            dota_lobby_password="night-4",
        )
        self.assertEqual(self.source(), "series")

    def test_source_fixed_event_overriding_the_series_password(self):
        self.attach_to_series(
            series_mode=FIXED,
            series_password="night-4",
            dota_lobby_password_mode=FIXED,
            dota_lobby_password="override",
        )
        self.assertEqual(self.source(), "event")

    def test_source_mode_differs_from_the_series(self):
        self.attach_to_series(series_mode=FIXED, series_password="night-4")
        self.assertEqual(self.source(), "event")

    def test_source_off_schedule_event(self):
        self.attach_to_series(series_mode=RANDOM, is_off_schedule=True)
        self.assertEqual(self.source(), "event")

    def test_registered_players_see_only_the_password(self):
        for status in (SignupStatus.APPROVED, SignupStatus.CONFIRMED):
            with self.subTest(status=status):
                resp = self.as_user(self.signed_up(status)).get(self.url())
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(
                    resp.data, {"password": self.event.dota_lobby_password}
                )

    def test_unaccepted_signups_and_outsiders_get_404(self):
        statuses = (
            SignupStatus.RSVP,
            SignupStatus.PENDING_APPROVAL,
            SignupStatus.WAITLISTED,
            SignupStatus.TENTATIVE,
            SignupStatus.REJECTED,
            SignupStatus.CANCELLED,
        )
        for status in statuses:
            with self.subTest(status=status):
                resp = self.as_user(self.signed_up(status)).get(self.url())
                self.assertEqual(resp.status_code, 404)
        for user in (self.unrelated_user, self.league_staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.as_user(user).get(self.url()).status_code, 404)
        self.assertEqual(APIClient().get(self.url()).status_code, 404)
        self.assertEqual(
            self.as_user(self.admin).get("/api/events/abc/lobby-password/").status_code,
            404,
        )

    def test_rostered_members_and_captains_see_it(self):
        captain = self.make_user("rostered_captain")
        member = self.make_user("rostered_member")
        team = Team.objects.create(
            tournament=self.tournament, name="Owls", captain=captain
        )
        team.members.add(member)
        for user in (captain, member):
            with self.subTest(user=user.username):
                self.assertTrue(is_registered_for_event(user, self.event))
                resp = self.as_user(user).get(self.url())
                self.assertEqual(resp.status_code, 200)

    def test_losing_the_signup_hides_it_again(self):
        user = self.signed_up(SignupStatus.CONFIRMED)
        self.assertEqual(self.as_user(user).get(self.url()).status_code, 200)
        EventSignup.objects.filter(user=user).update(status=SignupStatus.CANCELLED)
        self.assertEqual(self.as_user(user).get(self.url()).status_code, 404)

    def test_password_absent_from_event_payloads(self):
        password = self.event.dota_lobby_password
        confirmed = self.signed_up(SignupStatus.CONFIRMED)
        for user in (None, confirmed, self.admin):
            client = APIClient()
            if user:
                client.force_authenticate(user)
            for path in (
                f"/api/events/{self.event.pk}/",
                "/api/events/",
                f"/api/tournaments/{self.tournament.pk}/",
            ):
                with self.subTest(user=user and user.username, path=path):
                    resp = client.get(path)
                    self.assertNotIn(password, resp.content.decode())
        self.assertNotIn("dota_lobby_password", EventSerializer(self.event).data)
        self.assertIn("dota_lobby_password_mode", EventSerializer(self.event).data)

    @override_settings(INTERNAL_SERVICE_TOKEN="test-internal-token")
    def test_password_absent_from_celery_event_data(self):
        resp = APIClient().get(
            f"/api/internal/events/{self.event.pk}/full/",
            HTTP_X_INTERNAL_TOKEN="test-internal-token",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.event.dota_lobby_password, resp.content.decode())


class SeriesPasswordTests(EventTestCase):
    def setUp(self):
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=3,
            time_of_day=time(19, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        self.client = APIClient()

    def url(self, suffix=""):
        return f"/api/events/repeaters/{self.repeater.pk}/{suffix}"

    @patch("events.views.sync_future_events", return_value=[])
    def test_fixed_series_password(self, _sync):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            self.url(), {"dota_lobby_password_mode": FIXED}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        resp = self.client.patch(
            self.url(),
            {"dota_lobby_password_mode": FIXED, "dota_lobby_password": "series"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertNotIn("dota_lobby_password", resp.data)
        self.repeater.refresh_from_db()
        self.assertEqual(self.repeater.dota_lobby_password, "series")

        resp = self.client.get(self.url("lobby-password/"))
        self.assertEqual(
            resp.data, {"mode": FIXED, "password": "series", "can_manage": True}
        )

        self.client.patch(
            self.url(), {"dota_lobby_password_mode": RANDOM}, format="json"
        )
        self.repeater.refresh_from_db()
        self.assertEqual(self.repeater.dota_lobby_password, "")

    def test_series_password_is_staff_only(self):
        self.repeater.dota_lobby_password_mode = FIXED
        self.repeater.dota_lobby_password = "hidden"
        self.repeater.save()
        for user in (self.league_staff, self.unrelated_user, self.user):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(
                    self.client.get(self.url("lobby-password/")).status_code, 404
                )
        self.client.force_authenticate(None)
        for path in (self.url(), "/api/events/repeaters/"):
            self.assertNotIn("hidden", self.client.get(path).content.decode())


class TournamentLobbyFieldsTests(EventPasswordApiTestCase):
    def test_event_tournament_lobby_settings_are_read_only(self):
        url = f"/api/tournaments/{self.tournament.pk}/"
        resp = self.as_user(self.admin).patch(
            url, {"dota_lobby_mode": DotaLobbyMode.OFF}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("dota_lobby_mode", resp.data)
        # Sending the current values back (a full form save) is fine.
        resp = self.as_user(self.admin).patch(
            url, {"dota_lobby_mode": DotaLobbyMode.MANUAL, "name": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_standalone_tournament_keeps_its_own_settings(self):
        standalone = Tournament.objects.create(
            name="Standalone", date_played=tz.now(), league=self.league
        )
        resp = self.as_user(self.admin).patch(
            f"/api/tournaments/{standalone.pk}/",
            {"dota_lobby_mode": DotaLobbyMode.MANUAL},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        standalone.refresh_from_db()
        self.assertTrue(_is_generated(standalone.dota_lobby_password))


@override_settings(
    DOTA_LOBBY_ENABLED=True, DOTA_LOBBY_REF_PREFIX="game", DOTA_LOBBY_REGION=""
)
class LobbyCreateUsesEventPasswordTests(EventPasswordApiTestCase):
    def test_claim_snapshots_the_event_password(self):
        from lobby import services
        from lobby.tests.helpers import make_game

        self.event.dota_lobby_password_mode = FIXED
        self.event.dota_lobby_password = "from-the-event"
        self.event.game_mode = GameMode.CAPTAINS_MODE
        self.event.save()
        from events.services import sync_tournament_from_event

        sync_tournament_from_event(self.event)
        self.tournament.refresh_from_db()
        self.tournament.state = "in_progress"
        self.tournament.save()
        game = make_game(self.tournament)
        claim = services.claim_lobby(game.pk, trigger="manual")
        self.assertTrue(claim.created, claim.eligibility)
        self.assertEqual(claim.game_lobby.password, "from-the-event")
        self.assertEqual(
            services.create_body(claim.game_lobby)["password"], "from-the-event"
        )
        self.assertNotIn("password", claim.game_lobby.request)
