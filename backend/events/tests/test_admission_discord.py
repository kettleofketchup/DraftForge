from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, GameType
from discordbot.models import DiscordMessageLog
from events.admission import SELF_SERVE_DISABLED_MESSAGE
from events.constants import EventState
from events.discord.components import build_announcement_components
from events.discord.embeds import STATE_NOTICES, build_announcement_v2
from events.discord.handlers import (
    handle_battle_cup_submit,
    handle_rank_medal_select,
    handle_rank_status_select,
    handle_screenshot_upload,
    handle_signup_button,
    handle_signup_modal_submit,
    handle_tentative_button,
)
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


class DiscordFollowUpAdmissionTests(EventTestCase):
    """Flag turned off after the modal opened: later steps write nothing."""

    def setUp(self) -> None:
        self.closed = self.make_event(
            allow_user_signups=False, game_type=GameType.DOTA2
        )
        self.player = self.make_user()
        self.player.discordId = DISCORD_ID
        self.player.save()

    def _assert_untouched(self) -> None:
        self.assertFalse(
            PlayerDotaProfile.objects.filter(org_user__user=self.player).exists()
        )
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_modal_submit_refused_before_profile_write(self) -> None:
        result = handle_signup_modal_submit(
            self.closed.pk,
            DISCORD_ID,
            game_type=GameType.DOTA2,
            values={"friend_id": "12345", "rank_status": "active"},
        )

        self.assertEqual(
            result, {"action": "error", "message": SELF_SERVE_DISABLED_MESSAGE}
        )
        self._assert_untouched()

    def test_rank_steps_refused_before_profile_write(self) -> None:
        pk = self.closed.pk
        self.assertIsNone(handle_rank_status_select(pk, DISCORD_ID, "active"))
        for result in (
            handle_rank_medal_select(pk, DISCORD_ID, "Legend"),
            handle_battle_cup_submit(pk, DISCORD_ID, "3"),
        ):
            self.assertEqual(
                result, {"action": "error", "message": SELF_SERVE_DISABLED_MESSAGE}
            )
        self._assert_untouched()

    def test_screenshot_upload_refused_before_profile_write(self) -> None:
        result = handle_screenshot_upload(
            self.closed.pk, DISCORD_ID, "rank", "https://cdn.example/r.png"
        )

        self.assertEqual(
            result, {"success": False, "message": SELF_SERVE_DISABLED_MESSAGE}
        )
        self._assert_untouched()


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

    def _ids_in_state(self, state: EventState, **overrides: object) -> list[str]:
        event = self.make_event(state=state, allow_user_signups=True, **overrides)
        return _custom_ids(build_announcement_components(event))

    def test_buttons_per_state(self) -> None:
        expected = {
            EventState.UPCOMING: {"event_decline"},
            EventState.SIGNUPS_OPEN: {
                "event_signup",
                "event_tentative",
                "event_decline",
            },
            EventState.ROLL_CALL: {"event_decline"},
            EventState.IN_PROGRESS: set(),
            EventState.COMPLETED: set(),
            EventState.CANCELLED: set(),
        }
        for state, buttons in expected.items():
            with self.subTest(state=state):
                ids = self._ids_in_state(state)
                self.assertEqual({i.split(":")[0] for i in ids}, buttons)

    def test_closed_post_without_actions_has_no_empty_row(self) -> None:
        event = self.make_event(state=EventState.COMPLETED)
        self.assertEqual(build_announcement_components(event), [])

    def _schema_ids(self, state: EventState, **extra: object) -> list[str]:
        schema = EventTaskSchema(
            id=self.event.pk,
            name=self.event.name,
            state=state,
            scheduled_at=self.event.scheduled_at,
            allow_user_signups=True,
            **extra,
        )
        return [
            i.split(":")[0] for i in _custom_ids(build_announcement_components(schema))
        ]

    def test_notify_me_stays_after_the_event_closes(self) -> None:
        ids = self._schema_ids(EventState.CANCELLED, event_repeater_id=1)
        self.assertEqual(ids, ["event_notify"])

    def test_task_schema_buttons_follow_state(self) -> None:
        self.assertEqual(self._schema_ids(EventState.ROLL_CALL), ["event_decline"])


@patch("events.discord.embeds.get_event_signups", return_value=[])
class AnnouncementStatusLineTests(EventTestCase):
    def _description(self, state: EventState) -> str:
        event = self.make_event(state=state, description="Weekly inhouse.")
        return build_announcement_v2(event)["embeds"][0]["description"]

    def test_open_signups_has_no_status_line(self, _signups: MagicMock) -> None:
        self.assertEqual(self._description(EventState.SIGNUPS_OPEN), "Weekly inhouse.")

    def test_status_line_per_state(self, _signups: MagicMock) -> None:
        for state, notice in STATE_NOTICES.items():
            with self.subTest(state=state):
                self.assertEqual(
                    self._description(state), f"**{notice}**\n\nWeekly inhouse."
                )

    def test_every_non_open_state_has_a_status_line(self, _signups: MagicMock) -> None:
        self.assertEqual(
            set(STATE_NOTICES), set(EventState) - {EventState.SIGNUPS_OPEN}
        )


class AnnouncementPayloadStateTests(EventTestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="test-internal-token")
    def test_task_schema_reads_flag_from_internal_payload(self) -> None:
        event = self.make_event(allow_user_signups=False)
        resp = APIClient().get(
            f"/api/internal/events/{event.pk}/full/",
            HTTP_X_INTERNAL_TOKEN="test-internal-token",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("allow_user_signups", data)
        schema = EventTaskSchema.model_validate(data)
        self.assertFalse(schema.allow_user_signups)
        self.assertEqual(schema.state, EventState.SIGNUPS_OPEN)


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
