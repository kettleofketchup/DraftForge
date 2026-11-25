"""Discord message previews built through the same builders and gates as the tasks.

Reads only: never sends, saves or calls the internal API. Every builder gets
its signups injected so none of them loops back.
"""

import copy
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from app.models import CustomUser
from discordbot.payload_schema import DiscordMessage
from discordbot.payloads import (
    ChannelMessagePayload,
    build_channel_message_payload,
    build_dm_payload,
)
from discordbot.schemas import DiscordEventStateSchema
from events.capacity import with_signup_counts
from events.constants import EventState
from events.discord.embeds import (
    build_announcement_notice,
    build_announcement_v2,
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_scheduled_event_payload,
    build_scheduled_event_sync_payload,
    build_subscriber_dm_embed,
)
from events.discord.gates import (
    Destination,
    GateResult,
    announcement_branch,
    announcement_notice_gate,
    announcement_send_state,
    attendance_reminder_gate,
    new_event_post_gate,
    profile_reminder_gate,
    scheduled_event_gate,
    scheduled_event_sync_gate,
    signup_post_channel,
    signup_post_destination,
    signup_post_gate,
    signup_reminder_gate,
    start_mention_gate,
)
from events.discord.preview_codes import GateCode, NoteCode
from events.discord.preview_schema import (
    DiscordPreviewResponse,
    EventContext,
    Gate,
    Mentions,
    OrgDefaultsContext,
    PreviewContext,
    PreviewDestination,
    PreviewKind,
    ScheduledEventPreview,
    Variant,
)
from events.discord.preview_values import DiscordPreviewValuesSerializer
from events.discord.state import (
    latest_message_log_discord_id,
    load_discord_event_state,
    load_signups_for_embed,
    message_log_exists,
)
from events.models import Event, normalize_event_fields
from events.schemas import EventSignupSchema
from events.signup_schedule import (
    reapply_signup_open_policy_if_changed,
    signup_policy_snapshot,
)
from events.start_mention import build_start_mention_messages, start_mention_payload
from org.models import Organization
from org.permissions import has_org_staff_access
from telemetry.logging import get_logger

log = get_logger(__name__)

BUILDER_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    TypeError,
    ZoneInfoNotFoundError,
)


class PreviewInputError(Exception):
    """The form values cannot be turned into a message."""


@dataclass
class _Source:
    event: Event
    signups: Sequence[EventSignupSchema]
    discord_state: DiscordEventStateSchema
    saved: bool


@dataclass
class _Built:
    gate: GateResult
    destination: Destination | None = None
    messages: list[DiscordMessage] = field(default_factory=list)
    variants: list[Variant] = field(default_factory=list)
    scheduled_event: ScheduledEventPreview | None = None
    notes: list[NoteCode] = field(default_factory=list)
    note_args: dict[str, str] = field(default_factory=dict)
    mentions: dict[str, str] = field(default_factory=dict)


def _message(wire: ChannelMessagePayload) -> tuple[DiscordMessage, str | None]:
    body = wire["body"]
    if wire["path_kind"] == "threads":
        return DiscordMessage.model_validate(body["message"]), body["name"]
    return DiscordMessage.model_validate(body), None


def _in_send_state(event: Event) -> Event:
    send_event = copy.copy(event)
    send_event.state = announcement_send_state()
    return send_event


def _fired(source: str, event: Event) -> bool:
    return event.pk is not None and message_log_exists(source, event.pk)


def _announcement_channel(event: Event) -> Destination:
    return Destination(
        type="channel", channel_id=event.discord_announcement_channel_id or None
    )


def _signup_wire(event: Event, result: dict[str, Any]) -> ChannelMessagePayload:
    return build_channel_message_payload(
        result["embeds"],
        components=result["components"],
        content=result.get("content"),
        allowed_mentions=result.get("allowed_mentions"),
        forum_thread_name=event.discord_event_title or event.name,
    )


def _fallback_wire(result: dict[str, Any]) -> ChannelMessagePayload:
    return build_channel_message_payload(
        result["embeds"], components=result["components"]
    )


def _signup_permalink(event: Event, state: DiscordEventStateSchema) -> str | None:
    guild_id = event.organization.discord_server_id
    if not (guild_id and state.signup_posted and state.signup_message_id):
        return None
    channel_id = signup_post_channel(state)
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{state.signup_message_id}"


def _signup_post(src: _Source) -> _Built:
    event = src.event
    result = build_announcement_v2(_in_send_state(event), signups=src.signups)
    notes: list[NoteCode] = []
    if announcement_branch(event) == "fallback_signup_post":
        message, thread_name = _message(_fallback_wire(result))
        if result.get("content"):
            notes.append("fallback_drops_role_mentions")
    else:
        message, thread_name = _message(_signup_wire(event, result))
    destination = signup_post_destination(event)
    if destination is not None and thread_name is not None:
        destination = Destination(**{**asdict(destination), "thread_name": thread_name})

    variants: list[Variant] = []
    if event.state != announcement_send_state():
        notes.append("shown_as_posted_when_signups_open")
        if src.discord_state.signup_posted:
            current = build_announcement_v2(event, signups=src.signups)
            edit, _ = _message(_fallback_wire(current))
            variants.append(Variant(code="current_post", messages=[edit]))
            notes.append("edits_refresh_embed_only")

    gate = signup_post_gate(
        event,
        discord_state=src.discord_state,
        already_fired=_fired("event_announcement", event),
    )
    return _Built(
        gate=gate,
        destination=destination,
        messages=[message],
        variants=variants,
        notes=notes,
    )


def _announcement_notice(src: _Source) -> _Built:
    event = src.event
    send_event = _in_send_state(event)
    branch = announcement_branch(event)
    notes: list[NoteCode] = []
    if branch == "fallback_signup_post":
        result = build_announcement_v2(send_event, signups=src.signups)
        message, _ = _message(_fallback_wire(result))
        notes.append("fallback_replaces_notice")
        if result.get("content"):
            notes.append("fallback_drops_role_mentions")
        fired = _fired("event_announcement", event)
    else:
        link = _signup_permalink(event, src.discord_state)
        notice = build_announcement_notice(send_event, link)
        message, _ = _message(
            build_channel_message_payload(
                notice["embed"],
                content=notice.get("content"),
                allowed_mentions=notice.get("allowed_mentions"),
            )
        )
        if branch == "signup_post_and_notice":
            notes += [
                "signup_post_in_signup_channel",
                "notice_falls_back_if_signup_post_fails",
            ]
        if link is None:
            notes.append("signup_link_points_to_post")
        fired = _fired("event_notice", event)
    gate = announcement_notice_gate(
        event, discord_state=src.discord_state, already_fired=fired
    )
    return _Built(
        gate=gate,
        destination=_announcement_channel(event),
        messages=[message],
        notes=notes,
    )


def _channel_reminder(
    builder: Callable[..., dict[str, Any]],
    gate_fn: Callable[..., GateResult],
    source: str,
) -> Callable[[_Source], _Built]:
    def build(src: _Source) -> _Built:
        result = builder(src.event, signups=src.signups)
        message, _ = _message(
            build_channel_message_payload(
                result["embed"], components=result.get("components")
            )
        )
        gate = gate_fn(
            src.event,
            discord_state=src.discord_state,
            already_fired=_fired(source, src.event),
        )
        return _Built(
            gate=gate,
            destination=_announcement_channel(src.event),
            messages=[message],
        )

    return build


def _start_mention(src: _Source) -> _Built:
    event = src.event
    state = src.discord_state
    reply_to = state.signup_message_id if state.signup_posted else None
    built = build_start_mention_messages(event, src.signups)
    messages: list[DiscordMessage] = []
    for chunk in built.chunks:
        payload = start_mention_payload(chunk, reply_to)
        message, _ = _message(
            build_channel_message_payload(
                payload["embeds"],
                content=payload["content"],
                allowed_mentions=payload["allowed_mentions"],
                message_reference=payload["message_reference"],
            )
        )
        messages.append(message)
    mentioned = {i for chunk in built.chunks for i in chunk.user_ids}
    users = {
        s.user_data.discordId: s.display_name
        for s in src.signups
        if s.user_data and s.user_data.discordId in mentioned
    }
    reasons: list[GateCode] = list(
        start_mention_gate(
            event,
            discord_state=state,
            already_fired=_fired("start_mention", event),
        ).reasons
    )
    note_args: dict[str, str] = {}
    if not built.chunks:
        reasons.append("no_recipients")
        note_args["header"] = built.header
    return _Built(
        gate=GateResult(would_send=not reasons, reasons=reasons),
        destination=Destination(
            type="reply",
            channel_id=signup_post_channel(state) if reply_to else None,
            reply_to_message_id=reply_to,
        ),
        messages=messages,
        note_args=note_args,
        mentions=users,
    )


def _new_event_post(src: _Source) -> _Built:
    event = src.event
    message, _ = _message(build_channel_message_payload(build_new_event_embed(event)))
    reasons: list[GateCode] = []
    repeater = event.event_repeater
    if repeater is None:
        reasons.append("not_a_series")
    elif not repeater.discord_notify_new_events:
        reasons.append("toggle_off")
    reasons += new_event_post_gate(
        event,
        discord_state=src.discord_state,
        already_fired=_fired("new_event", event),
    ).reasons
    return _Built(
        gate=GateResult(would_send=not reasons, reasons=reasons),
        destination=_announcement_channel(event),
        messages=[message],
    )


def _signup_reminder(src: _Source) -> _Built:
    dm = build_subscriber_dm_embed(src.event, signups=src.signups)
    message = DiscordMessage.model_validate(
        build_dm_payload(None, dm["embed"], dm.get("components"))
    )
    gate = signup_reminder_gate(
        src.event,
        discord_state=src.discord_state,
        already_fired=_fired("signup_reminder", src.event),
    )
    return _Built(
        gate=gate,
        destination=Destination(type="dm", channel_id=None),
        messages=[message],
        notes=["dm_per_subscriber"],
    )


def _scheduled_event(src: _Source) -> _Built:
    event = src.event
    payload = build_scheduled_event_payload(event)
    fired = bool(src.discord_state.scheduled_event_id) or _fired(
        "create_discord_event", event
    )
    return _Built(
        gate=scheduled_event_gate(
            event, discord_state=src.discord_state, already_fired=fired
        ),
        destination=Destination(type="scheduled_event", channel_id=None),
        scheduled_event=ScheduledEventPreview.model_validate(payload),
    )


def _scheduled_event_sync(src: _Source) -> _Built:
    event = src.event
    sync = build_scheduled_event_sync_payload(
        event,
        event.signup_count,
        event.confirmed_count,
    )
    created_id = (
        latest_message_log_discord_id("create_discord_event", event.pk)
        if event.pk is not None
        else None
    )
    return _Built(
        gate=scheduled_event_sync_gate(
            event,
            scheduled_event_message_id=created_id,
            discord_state=src.discord_state,
        ),
        destination=Destination(type="scheduled_event", channel_id=None),
        scheduled_event=ScheduledEventPreview.model_validate(
            {**build_scheduled_event_payload(event), **sync}
        ),
        notes=["sync_overwrites_description"],
    )


KIND_BUILDERS: dict[PreviewKind, Callable[[_Source], _Built]] = {
    "scheduled_event": _scheduled_event,
    "scheduled_event_sync": _scheduled_event_sync,
    "signup_reminder": _signup_reminder,
    "profile_reminder": _channel_reminder(
        build_profile_reminder_embed, profile_reminder_gate, "profile_reminder"
    ),
    "attendance_reminder": _channel_reminder(
        build_attendance_reminder_embed,
        attendance_reminder_gate,
        "attendance_reminder",
    ),
    "start_mention": _start_mention,
    "signup_post": _signup_post,
    "announcement_notice": _announcement_notice,
    "new_event_post": _new_event_post,
}


def _authorize(user: CustomUser, organization: Organization) -> None:
    if not has_org_staff_access(user, organization):
        raise PermissionDenied("Only organization staff can preview Discord posts.")


def _load_event(event_id: int) -> Event:
    event = with_signup_counts(
        Event.objects.nocache()
        .select_related("organization", "event_repeater")
        .filter(pk=event_id)
    ).first()
    if event is None:
        raise Http404("Event not found.")
    return event


def _validated_values(values: dict[str, Any]) -> dict[str, Any]:
    serializer = DiscordPreviewValuesSerializer(data=values, partial=True)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def apply_event_overrides(event: Event, validated: dict[str, Any]) -> None:
    before = signup_policy_snapshot(event)
    upcoming = event.state == EventState.UPCOMING
    for attr, value in validated.items():
        setattr(event, attr, value)
    if upcoming:
        reapply_signup_open_policy_if_changed(event, before, timezone.now())
    normalize_event_fields(event)


def _response(
    kind: PreviewKind, built: _Built, *, saved: bool
) -> DiscordPreviewResponse:
    destination = (
        PreviewDestination(**asdict(built.destination)) if built.destination else None
    )
    return DiscordPreviewResponse(
        kind=kind,
        status="ok",
        saved=saved,
        gate=Gate(would_send=built.gate.would_send, reasons=built.gate.reasons),
        destination=destination,
        messages=built.messages,
        variants=built.variants,
        scheduled_event=built.scheduled_event,
        notes=built.notes,
        note_args=built.note_args,
        mentions=Mentions(users=built.mentions),
    )


def build_discord_preview(
    kind: PreviewKind,
    context: PreviewContext,
    values: dict[str, Any],
    user: CustomUser,
    *,
    open_signups: bool = False,
) -> DiscordPreviewResponse:
    if isinstance(context, OrgDefaultsContext):
        organization = Organization.objects.filter(pk=context.organization_id).first()
        if organization is None:
            raise Http404("Organization not found.")
        _authorize(user, organization)
        return DiscordPreviewResponse(
            kind=kind,
            status="unavailable",
            saved=False,
            gate=Gate(would_send=False),
        )
    if not isinstance(context, EventContext):
        raise NotImplementedError(context.type)

    event = _load_event(context.event_id)
    _authorize(user, event.organization)
    apply_event_overrides(event, _validated_values(values))
    source = _Source(
        event=event,
        signups=load_signups_for_embed(event.pk),
        discord_state=load_discord_event_state(event.pk),
        saved=True,
    )
    try:
        response = _response(kind, KIND_BUILDERS[kind](source), saved=source.saved)
    except BUILDER_ERRORS as exc:
        log.warning(
            "discord_preview_input_error",
            system="events",
            subsystem="discord_preview",
            kind=kind,
            context_type=context.type,
            event_id=event.pk,
            error_type=type(exc).__name__,
        )
        raise PreviewInputError("These values cannot be previewed.") from exc
    log.info(
        "discord_preview_built",
        system="events",
        subsystem="discord_preview",
        kind=kind,
        context_type=context.type,
        event_id=event.pk,
        status=response.status,
    )
    return response
