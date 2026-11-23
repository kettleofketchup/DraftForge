from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import HeroDraft
from events.models import Event
from org.models import Organization
from tournament.models import Game, Team, Tournament


class TaskScheduleEndpointTest(TestCase):
    def setUp(self):
        from events.models import Event, EventRepeater

        self.client = APIClient()
        self.org = Organization.objects.create(name="Schedule Test Org")
        # signup_reminder requires an event_repeater to be enabled (not misconfigured).
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Schedule Test Repeater",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        self.event = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Schedule Test Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=True,
            discord_signup_reminder_hours=6,
            discord_confirm_attendance=True,
            discord_confirm_attendance_hours=3,
            discord_profile_reminder=True,
            discord_profile_reminder_hours=4,
            discord_announcement=True,
            discord_announcement_channel_id="123456",
            discord_create_event=True,
        )
        user = CustomUser.objects.create_user(
            username="schedule_test_admin",
            password="test",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)

    def test_returns_task_list(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)

    def test_includes_all_enabled_tasks(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        task_names = [t["task"] for t in tasks]
        self.assertIn("announcement", task_names)
        # signup_reminder drives subscriber DMs; fired detection uses has_dms.
        self.assertIn("signup_reminder", task_names)
        self.assertIn("confirm_attendance", task_names)
        self.assertIn("profile_reminder", task_names)
        self.assertIn("scheduled_event", task_names)

    def test_includes_fires_at(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertIn("fires_at", reminder)
        self.assertIsNotNone(reminder["fires_at"])

    def test_disabled_tasks_show_disabled(self):
        from events.models import Event

        event = Event.objects.create(
            organization=self.org,
            name="Disabled Test",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=False,
            discord_confirm_attendance=False,
            discord_profile_reminder=False,
            discord_announcement=False,
            discord_create_event=False,
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        tasks = resp.json()
        for task in tasks:
            if task["task"] in (
                "signup_reminder",
                "confirm_attendance",
                "profile_reminder",
                "scheduled_event",
            ):
                self.assertEqual(
                    task["status"], "disabled", f"{task['task']} should be disabled"
                )

    def test_fired_tasks_detected(self):
        # signup_reminder fired status is driven by DiscordEventDM rows
        # (subscriber DMs sent), not DiscordMessageLog.
        from discordbot.models import DiscordEvent, DiscordEventDM, DMType
        from org.models import OrgUser

        user = CustomUser.objects.create_user(
            username="dm_recipient", password="x", discordId="999"
        )
        org_user = OrgUser.objects.create(user=user, organization=self.org)
        discord_event = DiscordEvent.objects.create(
            event=self.event, guild_id="guild123"
        )
        DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertEqual(reminder["status"], "fired")

    def test_announcement_misconfigured(self):
        """Announcement enabled but no channel ID → misconfigured."""
        from events.models import Event

        event = Event.objects.create(
            organization=self.org,
            name="Misconfigured Test",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=True,
            discord_announcement_channel_id="",  # empty
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        tasks = resp.json()
        ann = next(t for t in tasks if t["task"] == "announcement")
        self.assertEqual(ann["status"], "misconfigured")

    def test_requires_authentication(self):
        client = APIClient()  # not authenticated
        resp = client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 403)

    def test_404_for_nonexistent_event(self):
        resp = self.client.get("/api/events/99999/task-schedule/")
        self.assertEqual(resp.status_code, 404)

    def test_signup_post_can_fire_when_already_fired(self):
        """signup_post (and announcement) must stay re-fireable so admin can
        repost when the Discord post was deleted or needs a refresh. Other
        tasks (one-shot DMs, reminders) stay non-fireable once fired.
        """
        from discordbot.models import DiscordEvent, DiscordEventLog

        # Mark signup_post as fired via DiscordEventLog (the gate used by
        # _task() to set status='fired' for signup_post).
        discord_event = DiscordEvent.objects.create(
            event=self.event, guild_id="guild_repost"
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="send_signup_post",
            success=True,
        )
        # Required gating: signup_post needs discord_post_signups + channel id.
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "ch_signups"
        self.event.save()

        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        signup_post = next(t for t in tasks if t["task"] == "signup_post")
        self.assertEqual(signup_post["status"], "fired")
        self.assertTrue(
            signup_post["can_fire"],
            "signup_post must remain fireable after firing (Repost flow)",
        )


class FireSignupPostRepostTest(TestCase):
    """fire_event_task for signup_post must clear dedup state then dispatch
    send_event_announcement so the existing post is superseded by a fresh one.
    """

    def setUp(self):
        from events.models import Event

        self.client = APIClient()
        self.org = Organization.objects.create(name="Repost Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Repost Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=True,
            discord_announcement_channel_id="ch_ann",
        )
        # Both is_staff and is_superuser bypass the org-admin cascade
        # (see has_org_admin_access in org/permissions.py).
        self.admin = CustomUser.objects.create_superuser(
            username="repost_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def test_signup_post_repost_clears_dedup_and_dispatches(self):
        """The 409 idempotency guard is intentionally lifted for signup_post.
        We expect dedup state cleared AND celery dispatch."""
        from unittest.mock import patch

        from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog

        # Seed dedup state as if a prior post had succeeded.
        DiscordEventMsgSignup.objects.create(
            event_id=self.event.pk,
            channel_id="ch_ann",
            has_posted=True,
            message_id="old_msg",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            success=True,
            channel_id="ch_ann",
            embed_data={"title": "seed"},
        )

        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/signup_post/fire/"
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        # Dedup cleared on both gates.
        self.assertFalse(
            DiscordEventMsgSignup.objects.filter(
                event_id=self.event.pk, has_posted=True
            ).exists()
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement",
                source_id=self.event.pk,
                success=True,
            ).exists()
        )
        # send_event_announcement dispatched with the event id.
        mock_app.send_task.assert_called_once_with(
            "events.tasks.send_event_announcement", args=[self.event.pk]
        )


class ScheduledEventPastStartTest(TestCase):
    """Once an event's start has passed, Discord rejects a scheduled event for
    it, so the panel must not offer it and the fire endpoint must refuse it.
    """

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(
            name="Past Start Org", discord_server_id="111"
        )
        self.admin = CustomUser.objects.create_superuser(
            username="past_start_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def _event(self, starts_in: timedelta):
        from events.models import Event

        return Event.objects.create(
            organization=self.org,
            name="Past Start Event",
            state="signups_open",
            scheduled_at=timezone.now() + starts_in,
            discord_create_event=True,
        )

    def _scheduled_event_row(self, event):
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        return next(t for t in resp.json() if t["task"] == "scheduled_event")

    def test_past_start_is_disabled_and_not_fireable(self):
        row = self._scheduled_event_row(self._event(-timedelta(hours=2)))
        self.assertEqual(row["status"], "disabled")
        self.assertFalse(row["can_fire"])
        self.assertIn("Start time has passed", row["description"])

    def test_fired_past_start_stays_fired(self):
        from discordbot.models import DiscordEvent, DiscordEventLog

        event = self._event(-timedelta(hours=2))
        discord_event, _ = DiscordEvent.objects.get_or_create(
            event=event, defaults={"guild_id": "111"}
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="create_scheduled_event",
            success=True,
        )
        row = self._scheduled_event_row(event)
        self.assertEqual(row["status"], "fired")
        self.assertEqual(row["description"], "Creates a Discord guild scheduled event")

    def test_future_start_is_ready(self):
        row = self._scheduled_event_row(self._event(timedelta(hours=2)))
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["can_fire"])

    def test_fire_rejects_past_start(self):
        from unittest.mock import patch

        event = self._event(-timedelta(hours=2))
        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{event.pk}/task-schedule/scheduled_event/fire/"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["error"], "Event start time has passed")
        mock_app.send_task.assert_not_called()


class FireHeroDraftDmTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="HeroDraft DM Org")
        self.tournament = Tournament.objects.create(
            name="HeroDraft DM Tournament", date_played=timezone.now()
        )
        captain1 = CustomUser.objects.create_user(username="hd_cap1", password="x")
        captain2 = CustomUser.objects.create_user(username="hd_cap2", password="x")
        self.radiant = Team.objects.create(
            name="Radiant Team", tournament=self.tournament, captain=captain1
        )
        self.dire = Team.objects.create(
            name="Dire Team", tournament=self.tournament, captain=captain2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.radiant,
            dire_team=self.dire,
        )
        self.herodraft = HeroDraft.objects.create(game=self.game)
        self.event = Event.objects.create(
            organization=self.org,
            name="HeroDraft DM Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            tournament=self.tournament,
        )
        admin = CustomUser.objects.create_superuser(username="hd_admin", password="x")
        self.client.force_authenticate(user=admin)

    def test_resend_passes_game_id_to_task(self) -> None:
        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/herodraft_dm/fire/"
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        mock_app.send_task.assert_called_once()
        call = mock_app.send_task.call_args
        self.assertEqual(
            call.args[0], "events.tournament_tasks.send_tournament_herodraft_links"
        )
        args = list(call.kwargs.get("args", []))
        kwargs = dict(call.kwargs.get("kwargs") or {})
        params = dict(
            zip(
                [
                    "tournament_id",
                    "herodraft_id",
                    "game_id",
                    "radiant_name",
                    "dire_name",
                ],
                args,
            )
        )
        params.update(kwargs)
        self.assertEqual(params["tournament_id"], self.tournament.pk)
        self.assertEqual(params["herodraft_id"], self.herodraft.pk)
        self.assertEqual(params["game_id"], self.game.pk)
        self.assertEqual(params["radiant_name"], "Radiant Team")
        self.assertEqual(params["dire_name"], "Dire Team")
