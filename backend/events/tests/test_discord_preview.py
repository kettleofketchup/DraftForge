"""Discord previews equal what the tasks send, and never send or write."""

import ast
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from structlog.testing import capture_logs

from app.models import CustomUser
from discordbot.models import (
    DiscordEvent,
    DiscordEventLog,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)
from discordbot.payload_schema import DiscordMessage
from events.constants import (
    EventState,
    RepeatFrequency,
    SignupOpenMode,
    SignupStatus,
    StartMentionScope,
)
from events.discord.embeds import STATE_NOTICES
from events.discord.preview import (
    PreviewInputError,
    build_discord_preview,
)
from events.discord.preview_schema import (
    DiscordPreviewRequest,
    DiscordPreviewResponse,
    EventContext,
    OrgDefaultsContext,
    PreviewKind,
)
from events.discord.state import (
    load_discord_event_state,
    load_signups_for_embed,
    message_log_exists,
)
from events.models import Event, EventRepeater, EventSignup, RepeaterSubscription
from events.signup_schedule import compute_signups_open_at
from events.start_mention import build_start_mention_header
from events.tasks import (
    _create_discord_scheduled_event_impl,
    _send_event_announcement_impl,
    _send_new_event_notification_impl,
    _send_signup_update_impl,
    _send_start_mention_impl,
    _sync_discord_event_signups_impl,
    send_attendance_reminder,
    send_profile_reminder,
    send_subscriber_notifications,
)
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response
from org.models import Organization, OrgUser

BACKEND = str(Path(__file__).resolve().parents[2])
GUILD = "734185035623825559"
SIGNUP_CHANNEL = "5550001"
ANNOUNCE_CHANNEL = "5550009"
START = datetime(2030, 1, 5, 18, 0, tzinfo=timezone.utc)
ALL_KINDS: tuple[PreviewKind, ...] = (
    "scheduled_event",
    "scheduled_event_sync",
    "signup_reminder",
    "profile_reminder",
    "attendance_reminder",
    "start_mention",
    "signup_post",
    "announcement_notice",
    "new_event_post",
)


def _dump(message: DiscordMessage) -> dict[str, Any]:
    return message.model_dump(mode="json", exclude_unset=True)


def _without_reference(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k != "message_reference"}


@dataclass
class Captured:
    messages: list[dict[str, Any]] = field(default_factory=list)
    message_urls: list[str] = field(default_factory=list)
    edits: list[dict[str, Any]] = field(default_factory=list)
    scheduled_create: list[dict[str, Any]] = field(default_factory=list)
    scheduled_patch: list[dict[str, Any]] = field(default_factory=list)


class _PreviewTestCase(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=START.date(),
            created_by=self.admin,
            discord_notify_new_events=True,
        )
        self.ev = self.make_event(
            name="Weekly Inhouse",
            description="Snacks & <b>drinks</b>",
            scheduled_at=START,
            state=EventState.SIGNUPS_OPEN,
            max_players=10,
            allow_user_signups=True,
            event_repeater=self.repeater,
            discord_create_event=True,
            discord_sync_signups=True,
            discord_signup_reminder=True,
            discord_confirm_attendance=True,
            discord_profile_reminder=True,
            discord_start_mention=True,
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCE_CHANNEL,
            discord_signup_role_ids=["111", "222"],
            discord_announcement_role_ids=["333"],
        )
        for name, discord_id, status in [
            ("alpha", "100000000000000001", SignupStatus.RSVP),
            ("bravo", "100000000000000002", SignupStatus.CONFIRMED),
            ("charlie", "100000000000000003", SignupStatus.WAITLISTED),
            ("delta", "100000000000000004", SignupStatus.TENTATIVE),
            ("echo", "100000000000000005", SignupStatus.CANCELLED),
            ("nodiscord", None, SignupStatus.RSVP),
        ]:
            self._signup(self.ev, name, discord_id, status)

    def _signup(
        self, event: Event, name: str, discord_id: str | None, status: str
    ) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=name, password="x", discordId=discord_id
        )
        EventSignup.objects.create(event=event, user=user, status=status)
        return user

    def preview(
        self,
        kind: PreviewKind,
        values: dict[str, Any] | None = None,
        event: Event | None = None,
        user: CustomUser | None = None,
    ) -> DiscordPreviewResponse:
        return build_discord_preview(
            kind,
            EventContext(type="event", event_id=(event or self.ev).pk),
            values or {},
            user or self.admin,
        )

    def run_task(self, run: Callable[[], object]) -> Captured:
        captured = Captured()

        def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
            body = kwargs.get("json")
            if url.endswith("/users/@me/channels"):
                return _ok_response({"id": "dm-chan"})
            if method == "POST" and ("/messages" in url or url.endswith("/threads")):
                captured.messages.append(body)
                captured.message_urls.append(url)
            elif method == "PATCH":
                captured.edits.append(body)
            return _ok_response({"id": "m1"})

        def fake_post(url: str, **kwargs: Any) -> MagicMock:
            captured.scheduled_create.append(kwargs["json"])
            return MagicMock(
                status_code=200, json=MagicMock(return_value={"id": "888"})
            )

        def fake_patch(url: str, **kwargs: Any) -> MagicMock:
            captured.scheduled_patch.append(kwargs["json"])
            return MagicMock(status_code=200, json=MagicMock(return_value={}))

        with ExitStack() as stack:
            stack.enter_context(override_settings(TEST=False))
            stack.enter_context(
                patch(
                    "discordbot.utils._rate_limited_request", side_effect=fake_request
                )
            )
            stack.enter_context(patch("events.tasks.req.post", side_effect=fake_post))
            stack.enter_context(patch("events.tasks.req.patch", side_effect=fake_patch))
            for target in ("events.tasks", "events.discord.embeds"):
                stack.enter_context(
                    patch(f"{target}.get_event_signups", load_signups_for_embed)
                )
            stack.enter_context(
                patch("events.tasks.get_discord_event_state", load_discord_event_state)
            )
            stack.enter_context(
                patch("events.tasks.check_message_log_exists", message_log_exists)
            )
            run()
        return captured


class PreviewParityTest(_PreviewTestCase):
    def test_parity_signup_post(self) -> None:
        response = self.preview("signup_post")
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))

        thread = sent.messages[0]
        self.assertTrue(sent.message_urls[0].endswith(f"{SIGNUP_CHANNEL}/threads"))
        self.assertEqual([_dump(m) for m in response.messages], [thread["message"]])
        self.assertEqual(response.destination.type, "forum_thread")
        self.assertEqual(response.destination.channel_id, SIGNUP_CHANNEL)
        self.assertEqual(response.destination.thread_name, thread["name"])
        self.assertEqual(response.destination.fallback_channel_id, ANNOUNCE_CHANNEL)
        self.assertTrue(response.gate.would_send, response.gate.reasons)

    def test_parity_announcement_notice(self) -> None:
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))
        response = self.preview("announcement_notice")

        self.assertEqual(len(sent.messages), 2)
        self.assertEqual([_dump(m) for m in response.messages], [sent.messages[1]])
        self.assertIn(
            f"https://discord.com/channels/{GUILD}/{SIGNUP_CHANNEL}/m1",
            response.messages[0].embeds[0].description,
        )
        self.assertEqual(response.destination.channel_id, ANNOUNCE_CHANNEL)

    def test_parity_attendance_reminder(self) -> None:
        response = self.preview("attendance_reminder")
        sent = self.run_task(lambda: send_attendance_reminder(self.ev.pk))
        self.assertEqual([_dump(m) for m in response.messages], sent.messages)
        self.assertTrue(sent.message_urls[0].endswith(f"{ANNOUNCE_CHANNEL}/messages"))
        self.assertEqual(response.destination.channel_id, ANNOUNCE_CHANNEL)

    def test_parity_profile_reminder(self) -> None:
        response = self.preview("profile_reminder")
        sent = self.run_task(lambda: send_profile_reminder(self.ev.pk))
        self.assertEqual([_dump(m) for m in response.messages], sent.messages)
        self.assertEqual(len(sent.messages), 1)

    def test_parity_start_mention_both_scopes_with_chunks(self) -> None:
        for i in range(85):
            self._signup(
                self.ev, f"bulk{i}", f"2000000000000{i:05d}", SignupStatus.RSVP
            )
        DiscordEventMsgSignup.objects.create(
            event=self.ev,
            channel_id=SIGNUP_CHANNEL,
            thread_id="5550002",
            message_id="5550003",
            has_posted=True,
        )
        Event.objects.filter(pk=self.ev.pk).update(state=EventState.ROLL_CALL)
        for scope in (StartMentionScope.ALL_ACTIVE, StartMentionScope.MAIN):
            with self.subTest(scope=scope):
                DiscordMessageLog.objects.filter(source="start_mention").delete()
                Event.objects.filter(pk=self.ev.pk).update(
                    discord_start_mention_scope=scope
                )
                response = self.preview("start_mention")
                sent = self.run_task(lambda: _send_start_mention_impl(self.ev.pk, None))

                self.assertEqual(len(sent.messages), 2)
                self.assertEqual(
                    [_dump(m) for m in response.messages],
                    [_without_reference(b) for b in sent.messages],
                )
                for body in sent.messages:
                    self.assertEqual(
                        body["message_reference"],
                        {
                            "message_id": response.destination.reply_to_message_id,
                            "fail_if_not_exists": False,
                        },
                    )
                self.assertTrue(
                    sent.message_urls[0].endswith(
                        f"/{response.destination.channel_id}/messages"
                    )
                )
                self.assertEqual(
                    response.mentions.users["100000000000000001"],
                    "alpha",
                )
                self.assertNotIn("100000000000000005", response.mentions.users)

    def test_start_mention_without_recipients_reports_no_recipients(self) -> None:
        EventSignup.objects.filter(event=self.ev).update(status=SignupStatus.CANCELLED)
        DiscordEventMsgSignup.objects.create(
            event=self.ev,
            channel_id=SIGNUP_CHANNEL,
            thread_id="5550002",
            message_id="5550003",
            has_posted=True,
        )
        Event.objects.filter(pk=self.ev.pk).update(state=EventState.ROLL_CALL)

        response = self.preview("start_mention")
        sent = self.run_task(lambda: _send_start_mention_impl(self.ev.pk, None))

        self.assertEqual(response.messages, [])
        self.assertIn("no_recipients", response.gate.reasons)
        self.assertFalse(response.gate.would_send)
        self.assertEqual(
            response.note_args["header"],
            build_start_mention_header(Event.objects.get(pk=self.ev.pk)),
        )
        self.assertEqual(sent.messages, [])

    def test_parity_new_event_post(self) -> None:
        response = self.preview("new_event_post")
        sent = self.run_task(lambda: _send_new_event_notification_impl(self.ev.pk))
        self.assertEqual([_dump(m) for m in response.messages], sent.messages)
        self.assertTrue(response.gate.would_send, response.gate.reasons)

    def test_parity_signup_reminder_one_dm_per_subscriber(self) -> None:
        DiscordEvent.objects.create(event=self.ev, guild_id=GUILD)
        signed_up = CustomUser.objects.get(username="alpha")
        RepeaterSubscription.objects.create(
            event_repeater=self.repeater, user=signed_up
        )
        for name, discord_id in [
            ("sub1", "300000000000000001"),
            ("sub2", "300000000000000002"),
        ]:
            user = CustomUser.objects.create_user(
                username=name, password="x", discordId=discord_id
            )
            RepeaterSubscription.objects.create(event_repeater=self.repeater, user=user)

        response = self.preview("signup_reminder")
        sent = self.run_task(lambda: send_subscriber_notifications(self.ev.pk))

        self.assertEqual(len(sent.messages), 2)
        self.assertEqual(len(response.messages), 1)
        for body in sent.messages:
            self.assertEqual(_dump(response.messages[0]), body)
        self.assertEqual(response.destination.type, "dm")
        self.assertIn("dm_per_subscriber", response.notes)

    def test_parity_scheduled_event(self) -> None:
        response = self.preview("scheduled_event")
        sent = self.run_task(lambda: _create_discord_scheduled_event_impl(self.ev.pk))

        self.assertEqual(response.messages, [])
        body = sent.scheduled_create[0]
        self.assertEqual(
            response.scheduled_event.model_dump(),
            {
                key: body[key]
                for key in (
                    "name",
                    "description",
                    "scheduled_start_time",
                    "scheduled_end_time",
                    "entity_metadata",
                )
            },
        )
        self.assertTrue(response.gate.would_send, response.gate.reasons)

    def test_parity_scheduled_event_sync(self) -> None:
        DiscordMessageLog.objects.create(
            source="create_discord_event",
            source_id=self.ev.pk,
            channel_id=GUILD,
            embed_data={},
            discord_message_id="777",
            success=True,
        )
        response = self.preview("scheduled_event_sync")
        sent = self.run_task(lambda: _sync_discord_event_signups_impl(self.ev.pk))

        self.assertEqual(
            response.scheduled_event.description,
            sent.scheduled_patch[0]["description"],
        )
        self.assertTrue(response.gate.would_send, response.gate.reasons)
        self.assertIn("sync_overwrites_description", response.notes)


class PreviewBranchTest(_PreviewTestCase):
    def test_signup_post_previewed_in_send_state(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(
            state=EventState.UPCOMING, discord_announcement=False
        )
        response = self.preview("signup_post")
        self.assertIn("state_not_signups_open", response.gate.reasons)
        self.assertIn("shown_as_posted_when_signups_open", response.notes)

        Event.objects.filter(pk=self.ev.pk).update(state=EventState.SIGNUPS_OPEN)
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))

        self.assertEqual(len(sent.messages), 1)
        self.assertEqual(
            [_dump(m) for m in response.messages], [sent.messages[0]["message"]]
        )
        text = response.model_dump_json()
        for notice in STATE_NOTICES.values():
            self.assertNotIn(notice, text)
        labels = [
            button.label
            for row in response.messages[0].components
            for button in getattr(row, "components", [])
        ]
        self.assertIn("Sign Up", labels)
        self.assertIn("Tentative", labels)

    def test_announcement_notice_fallback_branch(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(discord_post_signups=False)
        notice = self.preview("announcement_notice")
        signup = self.preview("signup_post")
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))

        self.assertEqual(len(sent.messages), 1)
        self.assertTrue(sent.message_urls[0].endswith(f"{ANNOUNCE_CHANNEL}/messages"))
        self.assertEqual([_dump(m) for m in notice.messages], sent.messages)
        self.assertEqual([_dump(m) for m in signup.messages], sent.messages)
        self.assertIn("fallback_replaces_notice", notice.notes)
        self.assertIn("fallback_drops_role_mentions", notice.notes)
        self.assertEqual(signup.destination.type, "channel")
        self.assertEqual(signup.destination.channel_id, ANNOUNCE_CHANNEL)

    def test_announcement_notice_both_branch_notes(self) -> None:
        response = self.preview("announcement_notice")
        self.assertEqual(len(response.messages), 1)
        self.assertEqual(response.messages[0].content, "<@&333>")
        self.assertEqual(
            set(response.notes),
            {
                "signup_post_in_signup_channel",
                "notice_falls_back_if_signup_post_fails",
                "signup_link_points_to_post",
            },
        )

    def test_announcement_notice_signup_only_branch(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(discord_announcement_channel_id="")
        notice = self.preview("announcement_notice")
        signup = self.preview("signup_post")
        self.assertIn("no_channel", notice.gate.reasons)
        self.assertFalse(notice.gate.would_send)
        self.assertTrue(signup.gate.would_send, signup.gate.reasons)
        self.assertEqual(signup.destination.type, "forum_thread")
        self.assertIsNone(signup.destination.fallback_channel_id)

    def test_current_post_variant_when_already_posted(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.ev,
            channel_id=SIGNUP_CHANNEL,
            message_id="5550003",
            channel_type="text",
            has_posted=True,
        )
        Event.objects.filter(pk=self.ev.pk).update(state=EventState.ROLL_CALL)
        response = self.preview("signup_post")
        sent = self.run_task(lambda: _send_signup_update_impl(self.ev.pk, None))

        self.assertEqual([v.code for v in response.variants], ["current_post"])
        self.assertEqual([_dump(m) for m in response.variants[0].messages], sent.edits)
        self.assertIn("edits_refresh_embed_only", response.notes)
        self.assertNotEqual(response.messages, response.variants[0].messages)

    def test_no_variant_when_state_is_send_state(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.ev, channel_id=SIGNUP_CHANNEL, message_id="1", has_posted=True
        )
        self.assertEqual(self.preview("signup_post").variants, [])

    def test_thread_name_truncated_to_100(self) -> None:
        title = "T" * 130
        Event.objects.filter(pk=self.ev.pk).update(discord_event_title=title)
        response = self.preview("signup_post")
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))
        self.assertEqual(response.destination.thread_name, "T" * 100)
        self.assertEqual(response.destination.thread_name, sent.messages[0]["name"])

    def test_description_entities_match_saved_send(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(description="Plain")
        response = self.preview(
            "signup_post", {"description": "Snacks & <b>drinks</b>"}
        )
        self.assertIn("Snacks &amp; <b>drinks</b>", response.model_dump_json())

        event = Event.objects.get(pk=self.ev.pk)
        event.description = "Snacks & <b>drinks</b>"
        event.save()
        sent = self.run_task(lambda: _send_event_announcement_impl(self.ev.pk))
        self.assertEqual(
            [_dump(m) for m in response.messages], [sent.messages[0]["message"]]
        )

    def test_no_discord_server_still_renders(self) -> None:
        self.org.discord_server_id = ""
        self.org.save()
        for kind in ("signup_reminder", "scheduled_event"):
            with self.subTest(kind=kind):
                response = self.preview(kind)
                self.assertEqual(response.status, "ok")
                self.assertIn("no_discord_server", response.gate.reasons)
                self.assertFalse(response.gate.would_send)
        self.assertTrue(self.preview("signup_reminder").messages)

    def test_no_channel_still_renders(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(discord_announcement_channel_id="")
        response = self.preview("attendance_reminder")
        self.assertEqual(response.status, "ok")
        self.assertTrue(response.messages)
        self.assertIn("no_channel", response.gate.reasons)
        self.assertIsNone(response.destination.channel_id)

    def test_new_event_post_toggle_read_from_repeater(self) -> None:
        EventRepeater.objects.filter(pk=self.repeater.pk).update(
            discord_notify_new_events=False
        )
        response = self.preview("new_event_post")
        self.assertEqual(response.gate.reasons[0], "toggle_off")
        self.assertTrue(response.messages)

    def test_new_event_post_without_series(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(event_repeater=None)
        self.assertIn("not_a_series", self.preview("new_event_post").gate.reasons)

    def test_already_sent_reported(self) -> None:
        DiscordMessageLog.objects.create(
            source="attendance_reminder",
            source_id=self.ev.pk,
            channel_id=ANNOUNCE_CHANNEL,
            embed_data={},
            success=True,
        )
        self.assertIn("already_sent", self.preview("attendance_reminder").gate.reasons)

    def test_org_defaults_unavailable(self) -> None:
        response = build_discord_preview(
            "signup_post",
            OrgDefaultsContext(type="org_defaults", organization_id=self.org.pk),
            {},
            self.admin,
        )
        self.assertEqual(response.status, "unavailable")
        self.assertEqual(response.messages, [])
        self.assertFalse(response.gate.would_send)


class PreviewNoSideEffectTest(_PreviewTestCase):
    @contextmanager
    def _guards(self) -> Iterator[MagicMock]:
        boom = AssertionError("network call during preview")
        with ExitStack() as stack:
            for name in ("get", "post", "patch", "put", "delete", "request"):
                stack.enter_context(patch(f"requests.{name}", side_effect=boom))
            for name in ("get", "post", "patch", "api_get"):
                stack.enter_context(
                    patch(f"app.internal_client.transport.{name}", side_effect=boom)
                )
            stack.enter_context(
                patch("discordbot.utils._rate_limited_request", side_effect=boom)
            )
            spy = stack.enter_context(
                patch("events.discord.embeds.get_event_signups", side_effect=boom)
            )
            yield spy

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            DiscordMessageLog.objects.count(),
            DiscordEvent.objects.count(),
            DiscordEventLog.objects.count(),
            Event.objects.count(),
            list(Event.objects.filter(pk=self.ev.pk).values())[0],
        )

    def test_no_side_effects_every_kind(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.ev, channel_id=SIGNUP_CHANNEL, message_id="9", has_posted=True
        )
        overrides = {
            "name": "Changed",
            "description": "New & improved",
            "discord_event_title": "Changed title",
            "discord_signup_role_ids": ["999"],
            "signup_open_mode": SignupOpenMode.SCHEDULED,
            "scheduled_at": "2030-02-01T18:00:00Z",
        }
        before = self._snapshot()
        for kind in ALL_KINDS:
            with self.subTest(kind=kind):
                with self._guards() as spy, CaptureQueriesContext(connection) as ctx:
                    response = self.preview(kind, overrides)
                self.assertEqual(response.status, "ok")
                self.assertEqual(spy.call_count, 0)
                writes = [
                    q["sql"]
                    for q in ctx.captured_queries
                    if q["sql"]
                    .lstrip()
                    .upper()
                    .startswith(("INSERT", "UPDATE", "DELETE"))
                ]
                self.assertEqual(writes, [])
        self.assertEqual(self._snapshot(), before)


class PreviewAccessTest(_PreviewTestCase):
    def test_non_staff_member_permission_denied(self) -> None:
        member = self.make_user()
        with self.assertRaises(PermissionDenied):
            self.preview("signup_post", user=member)

    def test_other_org_event_permission_denied(self) -> None:
        other_owner = CustomUser.objects.create_user(
            username="other_owner", password="x"
        )
        other_org = Organization.objects.create(name="Other Org", owner=other_owner)
        other_event = self.make_event(organization=other_org)
        with self.assertRaises(PermissionDenied):
            self.preview("signup_post", event=other_event)

    def test_missing_event_http404(self) -> None:
        with self.assertRaises(Http404):
            build_discord_preview(
                "signup_post",
                EventContext(type="event", event_id=999999),
                {},
                self.admin,
            )

    def test_org_defaults_other_org_permission_denied(self) -> None:
        other_owner = CustomUser.objects.create_user(
            username="other_owner", password="x"
        )
        other_org = Organization.objects.create(name="Other Org", owner=other_owner)
        with self.assertRaises(PermissionDenied):
            build_discord_preview(
                "signup_post",
                OrgDefaultsContext(type="org_defaults", organization_id=other_org.pk),
                {},
                self.admin,
            )

    def test_staff_member_allowed(self) -> None:
        staff = self.make_user()
        self.org.staff.add(staff)
        self.assertEqual(self.preview("signup_post", user=staff).status, "ok")

    def test_org_member_row_is_not_enough(self) -> None:
        member = self.make_user()
        self.assertTrue(OrgUser.objects.filter(user=member).exists())
        with self.assertRaises(PermissionDenied):
            self.preview("attendance_reminder", user=member)


class PreviewOverridesTest(_PreviewTestCase):
    def test_override_title_and_roles_shown(self) -> None:
        response = self.preview(
            "signup_post",
            {
                "discord_event_title": "Friday Inhouse",
                "discord_signup_role_ids": [444, "555"],
            },
        )
        self.assertEqual(response.destination.thread_name, "Friday Inhouse")
        self.assertEqual(response.messages[0].content, "<@&444> <@&555>")
        self.assertEqual(
            response.messages[0].allowed_mentions, {"roles": ["444", "555"]}
        )
        self.assertEqual(
            Event.objects.get(pk=self.ev.pk).discord_signup_role_ids, ["111", "222"]
        )

    def test_unknown_key_ignored(self) -> None:
        plain = self.preview("attendance_reminder")
        response = self.preview("attendance_reminder", {"not_a_field": 1})
        self.assertEqual(response, plain)

    def test_state_and_org_in_values_ignored(self) -> None:
        other_owner = CustomUser.objects.create_user(
            username="other_owner", password="x"
        )
        other_org = Organization.objects.create(
            name="Other Org", owner=other_owner, discord_server_id="1"
        )
        plain = self.preview("scheduled_event")
        response = self.preview(
            "scheduled_event",
            {
                "state": EventState.COMPLETED,
                "organization": other_org.pk,
                "id": 12345,
                "event_repeater": None,
            },
        )
        self.assertEqual(response, plain)

    def test_invalid_timezone_is_validation_error(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.preview("profile_reminder", {"timezone": "Not/AZone"})
        self.assertIn("timezone", ctx.exception.detail)

    def test_role_ids_invalid(self) -> None:
        for bad in (5, ["abc"], [str(i) for i in range(26)], [True]):
            with self.subTest(bad=bad), self.assertRaises(ValidationError) as ctx:
                self.preview("signup_post", {"discord_signup_role_ids": bad})
            self.assertIn("discord_signup_role_ids", ctx.exception.detail)

    def test_builder_value_error_becomes_preview_input_error_and_logs_no_values(
        self,
    ) -> None:
        secret = "Secret Event Name"
        with (
            patch(
                "events.discord.preview.build_new_event_embed",
                side_effect=ValueError("bad"),
            ),
            capture_logs() as logs,
            self.assertRaises(PreviewInputError),
        ):
            self.preview("new_event_post", {"name": secret})
        records = [r for r in logs if r["event"] == "discord_preview_input_error"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["system"], "events")
        self.assertEqual(records[0]["subsystem"], "discord_preview")
        self.assertNotIn("values", records[0])
        self.assertNotIn(secret, repr(logs))

    def test_built_log_has_no_values(self) -> None:
        with capture_logs() as logs:
            self.preview("signup_post", {"name": "Hidden Name"})
        records = [r for r in logs if r["event"] == "discord_preview_built"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "signup_post")
        self.assertEqual(records[0]["context_type"], "event")
        self.assertEqual(records[0]["event_id"], self.ev.pk)
        self.assertNotIn("Hidden Name", repr(logs))

    def test_signup_open_policy_overrides_honoured(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(
            state=EventState.UPCOMING,
            signup_open_mode=SignupOpenMode.MANUAL,
            signups_open_at=None,
        )
        seen: list[Event] = []

        def capture(event: Event, now: datetime) -> None:
            event.signups_open_at = compute_signups_open_at(
                event, event.scheduled_at, now
            )
            seen.append(event)

        with patch(
            "events.signup_schedule.apply_signup_open_policy", side_effect=capture
        ):
            self.preview(
                "signup_post",
                {
                    "signup_open_mode": SignupOpenMode.SCHEDULED,
                    "signups_open_hours_before": 5,
                },
            )
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].signup_open_mode, SignupOpenMode.SCHEDULED)
        self.assertEqual(seen[0].signups_open_at, START - timedelta(hours=5))
        self.assertIsNone(Event.objects.get(pk=self.ev.pk).signups_open_at)

    def test_request_forbids_extra_keys(self) -> None:
        with self.assertRaises(Exception):
            DiscordPreviewRequest.model_validate(
                {
                    "kind": "signup_post",
                    "context": {"type": "event", "event_id": 1},
                    "extra": True,
                }
            )
        with self.assertRaises(Exception):
            DiscordPreviewRequest.model_validate(
                {
                    "kind": "signup_post",
                    "context": {"type": "event", "event_id": 1, "x": 1},
                }
            )


class PreviewModuleBoundaryTest(_PreviewTestCase):
    def test_preview_schema_imports_without_django(self) -> None:
        events_dir = Path(BACKEND) / "events"
        code = (
            "import sys, types; "
            f"sys.path.append({BACKEND!r}); "
            "pkg = types.ModuleType('events'); "
            f"pkg.__path__ = [{str(events_dir)!r}]; "
            "sub = types.ModuleType('events.discord'); "
            f"sub.__path__ = [{str(events_dir / 'discord')!r}]; "
            "sys.modules['events'] = pkg; sys.modules['events.discord'] = sub; "
            "import events.discord.preview_schema as s; "
            "s.DiscordPreviewApi.model_json_schema(); "
            "assert 'django' not in sys.modules, 'django imported'"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_preview_module_imports_no_send_modules(self) -> None:
        source = (Path(BACKEND) / "events" / "discord" / "preview.py").read_text()
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for banned in ("discordbot.utils", "requests", "app.internal_client"):
            self.assertFalse(
                any(m == banned or m.startswith(f"{banned}.") for m in imported),
                banned,
            )
