from dataclasses import replace
from typing import Literal

from discordbot.models import (
    DiscordEvent,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
)
from discordbot.permissions.schemas import ActionKind as A
from discordbot.permissions.schemas import PermissionChecksRequest, ResolvedCheckInput
from discordbot.permissions.service import preview_checks
from events.discord.channels import (
    attendance_reminder_channel,
    new_event_channel,
    profile_reminder_channel,
)
from events.models import Event


def saved_event_checks(event: Event) -> list[ResolvedCheckInput]:
    checks: list[ResolvedCheckInput] = []

    def add(
        key: str,
        action: A,
        channel_id: str | None = None,
        *,
        source: Literal[
            "configured", "fallback", "posted", "prospective", "guild", "recipient"
        ] = "configured",
        role_ids: tuple[str, ...] = (),
        reference_present: bool | None = None,
        message_id: str | None = None,
        scheduled_event_id: str | None = None,
    ) -> None:
        checks.append(
            ResolvedCheckInput(
                key=key,
                action=action,
                channel_id=channel_id or None,
                destination_source=source,
                role_ids=role_ids,
                reference_present=reference_present,
                message_id=message_id,
                scheduled_event_id=scheduled_event_id,
            )
        )

    fallback = event.discord_announcement and bool(
        event.discord_announcement_channel_id
    )
    if event.discord_post_signups:
        if event.discord_post_signups_channel_id or not fallback:
            add(
                "signup_post",
                A.SIGNUP_CREATE,
                event.discord_post_signups_channel_id,
                role_ids=tuple(event.discord_signup_role_ids),
            )
        if fallback:
            add(
                "signup_fallback",
                A.SIGNUP_FALLBACK,
                event.discord_announcement_channel_id,
                source="fallback",
            )
    if event.discord_announcement:
        add(
            "announcement",
            A.ANNOUNCEMENT,
            event.discord_announcement_channel_id,
            role_ids=tuple(event.discord_announcement_role_ids),
        )
    for enabled, key, action, own, channel in (
        (
            event.discord_confirm_attendance,
            "attendance_reminder",
            A.ATTENDANCE_REMINDER,
            event.discord_confirm_attendance_channel_id,
            attendance_reminder_channel(event),
        ),
        (
            event.discord_profile_reminder,
            "profile_reminder",
            A.PROFILE_REMINDER,
            event.discord_profile_reminder_channel_id,
            profile_reminder_channel(event),
        ),
        (
            bool(
                event.event_repeater_id
                and event.event_repeater.discord_notify_new_events
            ),
            "new_event_notice",
            A.NEW_EVENT_NOTICE,
            event.discord_new_event_channel_id,
            new_event_channel(event),
        ),
    ):
        if enabled:
            add(key, action, channel, source="configured" if own else "fallback")

    state = (
        DiscordEvent.objects.filter(event=event)
        .select_related("signup_message", "announcement")
        .first()
    )
    signup: DiscordEventMsgSignup | None = state.signup_message if state else None
    announcement: DiscordEventMsgAnnouncement | None = (
        state.announcement if state else None
    )
    for message, key, action in (
        (signup, "signup_edit", A.SIGNUP_EDIT),
        (announcement, "announcement_edit", A.ANNOUNCEMENT_EDIT),
    ):
        if message and message.has_posted:
            add(
                key,
                action,
                message.thread_id or message.channel_id,
                source="posted",
                reference_present=True,
                message_id=message.message_id,
            )
    if event.discord_start_mention:
        if signup and signup.has_posted:
            add(
                "start_mention",
                A.START_MENTION,
                signup.thread_id or signup.channel_id,
                source="posted",
                reference_present=bool(signup.message_id),
                message_id=signup.message_id,
            )
        else:
            add(
                "start_mention",
                A.START_MENTION,
                event.discord_post_signups_channel_id
                or (event.discord_announcement_channel_id if fallback else None),
                source="prospective",
                reference_present=False,
            )
    if event.discord_create_event:
        add("scheduled_event_create", A.SCHEDULED_EVENT_CREATE, source="guild")
    if state and state.scheduled_event_id:
        for key, action in (
            ("scheduled_event_update", A.SCHEDULED_EVENT_UPDATE),
            ("scheduled_event_delete", A.SCHEDULED_EVENT_DELETE),
        ):
            add(
                key,
                action,
                source="guild",
                reference_present=True,
                scheduled_event_id=state.scheduled_event_id,
            )
    if event.discord_create_event and event.discord_mark_interested:
        add("mark_interested", A.MARK_INTERESTED, source="guild")
    for enabled, key, action in (
        (event.discord_signup_reminder, "signup_reminder", A.SIGNUP_REMINDER_DM),
        (event.discord_send_draft_link, "draft_dm", A.TOURNAMENT_DM),
        (event.discord_send_herodraft_link, "herodraft_dm", A.TOURNAMENT_DM),
    ):
        if enabled:
            add(key, action, source="recipient")
    return checks


def preview_event_checks(
    event: Event, body: PermissionChecksRequest
) -> list[ResolvedCheckInput]:
    checks = preview_checks(body.checks)
    state = DiscordEvent.objects.filter(event=event).first()
    if state and state.scheduled_event_id:
        checks = [
            replace(
                check,
                reference_present=True,
                scheduled_event_id=state.scheduled_event_id,
                destination_source="guild",
            )
            if check.action in (A.SCHEDULED_EVENT_UPDATE, A.SCHEDULED_EVENT_DELETE)
            else check
            for check in checks
        ]
    return checks
