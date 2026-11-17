from unittest.mock import MagicMock, patch

from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import DiscordMessageLog
from events.admission import SELF_SERVE_DISABLED_MESSAGE
from events.discord.components import build_announcement_components
from events.discord.handlers import handle_signup_button, handle_tentative_button
from events.discord.reactions import handle_reaction_signup
from events.models import EventSignup
from events.schemas import EventTaskSchema
from events.tests.base import EventTestCase
from org.models import PlayerDotaProfile

DISCORD_ID = "300000000000000001"


def _custom_ids(rows: list[dict[str, object]]) -> list[str]:
    return [c["custom_id"] for row in rows for c in row["components"]]  # type: ignore[index, union-attr]


class DiscordButtonAdmissionTests(EventTestCase):
    def setUp(self) -> None:
        self.closed = self.make_event(allow_user_signups=False)

    def _assert_refused(self, result: dict[str, object]) -> None:
        self.assertEqual(result["action"], "error")
        self.assertEqual(result["message"], SELF_SERVE_DISABLED_MESSAGE)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_signup_button_refused_before_profile_or_modal(self) -> None:
        users_before = CustomUser.objects.count()
        profiles_before = PlayerDotaProfile.objects.count()

        result = handle_signup_button(self.closed.pk, DISCORD_ID, "closed_clicker")

        self._assert_refused(result)
        self.assertEqual(PlayerDotaProfile.objects.count(), profiles_before)
        self.assertEqual(CustomUser.objects.count(), users_before)

    def test_tentative_button_refused(self) -> None:
        self._assert_refused(
            handle_tentative_button(self.closed.pk, DISCORD_ID, "closed_clicker")
        )

    def test_reaction_creates_no_signup(self) -> None:
        player = self.make_user()
        player.discordId = DISCORD_ID
        player.save()
        DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=self.closed.pk,
            discord_message_id="555000111",
            success=True,
        )

        success, detail = handle_reaction_signup("555000111", DISCORD_ID)

        self.assertFalse(success)
        self.assertEqual(detail, SELF_SERVE_DISABLED_MESSAGE)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())


class AnnouncementComponentsTests(EventTestCase):
    def _schema(self, allow_user_signups: bool) -> EventTaskSchema:
        event = self.make_event(allow_user_signups=allow_user_signups)
        return EventTaskSchema(
            id=event.pk,
            name=event.name,
            state=event.state,
            scheduled_at=event.scheduled_at,
            allow_user_signups=allow_user_signups,
        )

    def test_self_serve_buttons_hidden_when_disabled(self) -> None:
        ids = _custom_ids(build_announcement_components(self._schema(False)))
        self.assertTrue(any(i.startswith("event_decline:") for i in ids))
        self.assertFalse(any(i.startswith("event_signup:") for i in ids))
        self.assertFalse(any(i.startswith("event_tentative:") for i in ids))

    def test_self_serve_buttons_shown_when_enabled(self) -> None:
        ids = _custom_ids(build_announcement_components(self._schema(True)))
        self.assertTrue(any(i.startswith("event_signup:") for i in ids))
        self.assertTrue(any(i.startswith("event_tentative:") for i in ids))

    def test_task_schema_reads_flag_from_event_payload(self) -> None:
        event = self.make_event(allow_user_signups=False)
        client = APIClient()
        client.force_authenticate(self.admin)
        data = client.get(f"/api/events/{event.pk}/").json()
        self.assertIn("allow_user_signups", data)
        self.assertFalse(EventTaskSchema.model_validate(data).allow_user_signups)


class FlagChangeRepostTests(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.target = self.make_event()

    def _patch(self, body: dict[str, object]) -> MagicMock:
        with patch("events.views.notify_signup_changed") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.client.patch(
                    f"/api/events/{self.target.pk}/", body, format="json"
                )
            self.assertEqual(resp.status_code, 200, resp.content)
        return notify

    def test_flag_change_refreshes_signup_post(self) -> None:
        notify = self._patch({"allow_user_signups": False})
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].pk, self.target.pk)

    def test_unrelated_change_does_not_refresh(self) -> None:
        notify = self._patch({"description": "new text"})
        notify.assert_not_called()
