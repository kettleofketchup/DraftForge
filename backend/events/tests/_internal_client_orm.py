"""ORM-direct replacements for app.internal_client functions used in tests.

The production internal_client makes real HTTP calls to the public/internal API.
In Django unit tests data lives inside an unrolled transaction the HTTP server
can't see, so calls return 404/empty.

This module provides drop-in replacements that read/write directly from the
ORM, plus a DiscordTestMixin TestCase mixin that monkey-patches
``app.internal_client`` (and call sites that imported the symbol) for the
duration of each test.

Usage::

    from events.tests._internal_client_orm import DiscordTestMixin
    from events.tests.base import EventTestCase

    class MyTest(DiscordTestMixin, EventTestCase):
        ...
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from unittest.mock import patch

import requests
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from app.auth import InternalServiceUser
from app.internal_client import transport
from app.internal_client.discord import (
    begin_signup_delivery,
    clear_event_signup_state,
    complete_signup_delivery,
    get_signup_blocked_event_ids,
    mark_signup_delivery_sending,
)
from app.views import internal as internal_views
from discordbot import internal_signup_delivery_views as delivery_views
from discordbot.delivery_types import ClaimResult
from discordbot.models import (
    ChannelType,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)
from discordbot.schemas import DiscordEventStateSchema, MessageLogSchema
from events.capacity import with_signup_counts
from events.ledger import SignupActor
from events.models import Event, EventSignup, RepeaterSubscription
from events.ready_check import (
    READY_CHECK_HELD_MESSAGE,
    transition_with_ready_check,
)
from events.schemas import EventSignupSchema, EventTaskSchema, RepeaterSubscriberSchema
from events.serializers import EventSerializer, EventSignupSerializer

P = ParamSpec("P")
R = TypeVar("R")

_INTERNAL_VIEWS: dict[str, Callable[..., Any]] = {
    "/discord/signup-delivery/begin/": delivery_views.begin_signup_delivery,
    "/discord/signup-delivery/sending/": delivery_views.mark_signup_delivery_sending,
    "/discord/signup-delivery/complete/": delivery_views.complete_signup_delivery,
    "/discord/signup-delivery/blocked/": delivery_views.signup_delivery_blocked,
    "/discord/signup-message/clear/": internal_views.clear_event_signup_state,
}


def _call_internal_view(method: str, path: str, data: dict | None) -> requests.Response:
    factory = APIRequestFactory()
    url = f"/api/internal{path}"
    request = (
        factory.post(url, data, format="json")
        if method == "POST"
        else factory.get(url, data)
    )
    force_authenticate(request, user=InternalServiceUser())
    drf_response = _INTERNAL_VIEWS[path](request)
    drf_response.render()
    response = requests.Response()
    response.status_code = drf_response.status_code
    response._content = drf_response.content
    return response


def _via_internal_views(fn: Callable[P, R]) -> Callable[P, R]:
    """Run the real client against the real view, in-process."""

    @wraps(fn)
    def fake(*args: P.args, **kwargs: P.kwargs) -> R:
        with (
            patch.object(
                transport,
                "post",
                lambda path, data: _call_internal_view("POST", path, data),
            ),
            patch.object(
                transport,
                "get",
                lambda path, params=None: _call_internal_view("GET", path, params),
            ),
        ):
            return fn(*args, **kwargs)

    return fake


# ---- ORM-direct reads ----


def _get_event_signups_orm(event_id):
    """Read EventSignups directly from the ORM and return EventSignupSchema list."""

    qs = EventSignup.objects.filter(event_id=event_id).select_related("user", "event")
    return [EventSignupSchema.model_validate(EventSignupSerializer(s).data) for s in qs]


def _get_event_for_task_orm(pk):
    """Read full event data directly from the ORM and return EventTaskSchema."""

    try:
        event = with_signup_counts(
            Event.objects.select_related("organization", "event_repeater").filter(pk=pk)
        ).get()
    except Event.DoesNotExist:
        return None
    data = EventSerializer(event).data
    data["organization_id"] = event.organization_id
    data["organization_discord_server_id"] = event.organization.discord_server_id or ""
    data["organization_logo"] = event.organization.logo or ""
    data["event_repeater_id"] = event.event_repeater_id
    return EventTaskSchema.model_validate(data)


def _get_event_orm(pk):
    """Read event data; mimics transport.api_get response. Returns ResponseLike or None."""

    try:
        event = Event.objects.get(pk=pk)
    except Event.DoesNotExist:
        return _ResponseLike(404, {"error": "not found"})
    return _ResponseLike(200, EventSerializer(event).data)


def _get_events_list_orm(**params):
    """Mimic the public events list endpoint, supporting the filters our tests need."""

    qs = Event.objects.all()
    states = params.get("states")
    if states:
        state_list = [s.strip() for s in states.split(",") if s.strip()]
        qs = qs.filter(state__in=state_list)

    if params.get("has_repeater") == "true":
        qs = qs.filter(event_repeater__isnull=False)
    if params.get("has_announcement_channel") == "true":
        qs = qs.exclude(discord_announcement_channel_id="")
    signups_due_before = params.get("signups_due_before")
    if signups_due_before:
        qs = qs.filter(
            signups_open_at__isnull=False,
            signups_open_at__lte=datetime.fromisoformat(signups_due_before),
        )

    return [EventSerializer(e).data for e in qs]


def _get_discord_event_state_orm(event_id):
    """Mimic /discord/event-state/<event_id>/."""

    result = {
        "has_discord_event": False,
        "scheduled_event_id": None,
        "signup_posted": False,
        "fired_actions": [],
        "has_dms": False,
    }
    try:
        de = DiscordEvent.objects.get(event_id=event_id)
        result["has_discord_event"] = True
        result["discord_event_pk"] = de.pk
        result["scheduled_event_id"] = de.scheduled_event_id or None
        result["has_dms"] = DiscordEventDM.objects.filter(discord_event=de).exists()
    except DiscordEvent.DoesNotExist:
        pass

    signup_msg = DiscordEventMsgSignup.objects.filter(
        event_id=event_id, has_posted=True
    ).first()
    result["signup_posted"] = signup_msg is not None
    if signup_msg:
        result["signup_message_id"] = signup_msg.message_id
        result["signup_channel_id"] = signup_msg.channel_id
        result["signup_thread_id"] = signup_msg.thread_id
    return DiscordEventStateSchema.model_validate(result)


def _check_message_log_exists_orm(source, source_id):
    """Match the partial unique condition: NULL pending OR True succeeded
    rows count as 'exists'; False failed rows do not (allowing retry)."""

    return (
        DiscordMessageLog.objects.filter(source=source, source_id=source_id)
        .filter(Q(success__isnull=True) | Q(success=True))
        .exists()
    )


def _search_message_logs_orm(*args, **kwargs):
    """ORM-backed replacement accepting positional args or the keyword-only
    signature of search_message_logs."""

    if args:
        keys = ["source", "source_id", "success", "limit"]
        for i, val in enumerate(args):
            kwargs.setdefault(keys[i], val)

    qs = DiscordMessageLog.objects.all()
    if "source" in kwargs:
        qs = qs.filter(source=kwargs["source"])
    if "source_id" in kwargs:
        qs = qs.filter(source_id=kwargs["source_id"])
    success = kwargs.get("success")
    if success is not None:
        if isinstance(success, str):
            success = success.lower() == "true"
        qs = qs.filter(success=success)
    qs = qs.order_by("-created_at")
    limit = int(kwargs.get("limit") or 1)
    qs = qs[:limit]

    out = []
    for entry in qs:
        out.append(
            MessageLogSchema.model_validate(
                {
                    "id": entry.pk,
                    "source": entry.source,
                    "source_id": entry.source_id,
                    "channel_id": entry.channel_id,
                    "discord_message_id": entry.discord_message_id,
                    "status_code": entry.status_code,
                    "success": entry.success,
                    "response_data": entry.response_data,
                    "created_at": entry.created_at.isoformat()
                    if entry.created_at
                    else None,
                }
            )
        )
    return out


# ---- ORM-direct writes ----


def _create_message_log_orm(**data):
    log = DiscordMessageLog.objects.create(
        channel_id=str(data.get("channel_id", "")),
        embed_data=data.get("embed_data") or {},
        source=data.get("source", "unknown"),
        source_id=data.get("source_id"),
        discord_message_id=data.get("discord_message_id"),
        status_code=data.get("status_code"),
        response_data=data.get("response_data"),
        success=bool(data.get("success", False)),
    )
    return _ResponseLike(201, {"id": log.pk})


def _claim_discord_message_log_orm(
    *,
    source: str,
    source_id: int,
    channel_id: str,
    embed_data: dict,
    fired_by_user_id: int | None = None,
    tournament_log_id: int | None = None,
) -> int | None:
    return _claim_discord_message_log_result_orm(
        source=source,
        source_id=source_id,
        channel_id=channel_id,
        embed_data=embed_data,
        fired_by_user_id=fired_by_user_id,
        tournament_log_id=tournament_log_id,
    ).log_id


def _claim_discord_message_log_result_orm(
    *,
    source: str,
    source_id: int,
    channel_id: str,
    embed_data: dict,
    fired_by_user_id: int | None = None,
    tournament_log_id: int | None = None,
) -> ClaimResult:
    """ORM-backed lease claim — mirrors the HTTP endpoint."""

    create_kwargs = {
        "source": source,
        "source_id": source_id,
        "channel_id": str(channel_id),
        "embed_data": embed_data,
        "success": None,
        "claimed_at": timezone.now(),
    }
    if fired_by_user_id is not None:
        create_kwargs["fired_by_id"] = fired_by_user_id
    if tournament_log_id is not None:
        create_kwargs["tournament_log_id"] = tournament_log_id
    try:
        with transaction.atomic():
            row = DiscordMessageLog.objects.create(**create_kwargs)
        return ClaimResult("claimed", row.pk)
    except IntegrityError:
        return ClaimResult("held")


def _finalize_discord_message_log_orm(
    log_id,
    *,
    success,
    discord_message_id=None,
    status_code=None,
    response_data=None,
):
    """ORM-backed finalize — mirrors the HTTP endpoint."""

    update_fields = {"success": bool(success)}
    if discord_message_id is not None:
        update_fields["discord_message_id"] = discord_message_id
    if status_code is not None:
        update_fields["status_code"] = status_code
    if response_data is not None:
        update_fields["response_data"] = response_data

    updated = DiscordMessageLog.objects.filter(pk=log_id).update(**update_fields)
    if updated == 0:
        return _ResponseLike(410, {"detail": "log row not found (likely swept)"})
    return _ResponseLike(200, {})


def _create_event_log_orm(**data):
    try:
        de = DiscordEvent.objects.get(pk=data["discord_event_id"])
    except DiscordEvent.DoesNotExist:
        return _ResponseLike(404, {"error": "DiscordEvent not found"})
    fields = {
        "action": data.get("action"),
        "target_type": data.get("target_type"),
        "message_id": data.get("message_id"),
        "status_code": data.get("status_code"),
        "response_data": data.get("response_data"),
        "success": bool(data.get("success", False)),
        "error_message": data.get("error_message"),
        "message_log_id": data.get("message_log_id"),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    entry = DiscordEventLog.objects.create(discord_event=de, **fields)
    return _ResponseLike(201, {"id": entry.pk})


def _get_or_create_discord_event_orm(**data):
    de, created = DiscordEvent.objects.get_or_create(
        event_id=data["event_id"],
        defaults={"guild_id": data.get("guild_id", "")},
    )
    return _ResponseLike(201 if created else 200, {"id": de.pk, "created": created})


def _update_discord_event_orm(pk, **data):
    de = DiscordEvent.objects.get(pk=pk)
    for k, v in data.items():
        if hasattr(de, k):
            setattr(de, k, v)
    de.save()
    return _ResponseLike(200, {"id": de.pk})


def _create_or_update_signup_message_orm(**data):
    payload = dict(data)
    event_id = payload.pop("event_id")
    channel_id = payload.pop("channel_id")
    msg, created = DiscordEventMsgSignup.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": payload.get("channel_type", ChannelType.TEXT)},
    )
    for field in (
        "message_id",
        "thread_id",
        "channel_type",
        "has_posted",
        "message_last_updated",
    ):
        if field in payload:
            setattr(msg, field, payload[field])
    msg.save()
    return _ResponseLike(201 if created else 200, {"id": msg.pk, "created": created})


def _transition_event_state_orm(event_pk, new_state):
    """Mirror POST /api/internal/events/<pk>/transition/."""

    event = Event.objects.nocache().get(pk=event_pk)
    try:
        started = transition_with_ready_check(
            event, new_state, actor=SignupActor.system()
        )
    except ValueError as exc:
        return _ResponseLike(400, {"error": str(exc)})
    if not started:
        return _ResponseLike(
            409, {"code": "ready_check_held", "error": READY_CHECK_HELD_MESSAGE}
        )
    return _ResponseLike(200, {"id": event.pk, "state": event.state})


def _create_or_update_announcement_orm(**data):
    payload = dict(data)
    event_id = payload.pop("event_id")
    channel_id = payload.pop("channel_id")
    msg, created = DiscordEventMsgAnnouncement.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": payload.get("channel_type", ChannelType.TEXT)},
    )
    for field in ("message_id", "channel_type", "has_posted", "message_last_updated"):
        if field in payload:
            setattr(msg, field, payload[field])
    msg.save()
    return _ResponseLike(201 if created else 200, {"id": msg.pk, "created": created})


def _get_repeater_subscribers_orm(repeater_id):
    """Read RepeaterSubscriptions from the ORM and return RepeaterSubscriberSchema list.

    Mirrors what app/views/internal.py exposes — only subscribers with a
    non-empty discord_id are returned (DM target has to exist).
    """

    qs = RepeaterSubscription.objects.filter(
        event_repeater_id=repeater_id
    ).select_related("user")
    out = []
    for sub in qs:
        discord_id = getattr(sub.user, "discordId", "") or ""
        if not discord_id:
            continue
        out.append(
            RepeaterSubscriberSchema.model_validate(
                {
                    "user_pk": sub.user_id,
                    "discord_id": discord_id,
                    "org_user_pk": None,
                }
            )
        )
    return out


# ---- Helper ----


class _ResponseLike:
    """Mimics the bits of a ``requests.Response`` callers rely on."""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


# ---- Mixin ----


# Map of attribute → ORM-backed callable.
# ``patch.multiple`` uses these on app.internal_client AND on every other module
# that imported the symbol directly (hence the second pass on call sites).
_PATCH_MAP = {
    "get_event_signups": _get_event_signups_orm,
    "get_event_for_task": _get_event_for_task_orm,
    "get_event": _get_event_orm,
    "get_events_list": _get_events_list_orm,
    "get_discord_event_state": _get_discord_event_state_orm,
    "check_message_log_exists": _check_message_log_exists_orm,
    "search_message_logs": _search_message_logs_orm,
    "create_message_log": _create_message_log_orm,
    "claim_discord_message_log": _claim_discord_message_log_orm,
    "claim_discord_message_log_result": _claim_discord_message_log_result_orm,
    "finalize_discord_message_log": _finalize_discord_message_log_orm,
    "create_event_log": _create_event_log_orm,
    "get_or_create_discord_event": _get_or_create_discord_event_orm,
    "update_discord_event": _update_discord_event_orm,
    "create_or_update_signup_message": _create_or_update_signup_message_orm,
    "clear_event_signup_state": _via_internal_views(clear_event_signup_state),
    "begin_signup_delivery": _via_internal_views(begin_signup_delivery),
    "mark_signup_delivery_sending": _via_internal_views(mark_signup_delivery_sending),
    "complete_signup_delivery": _via_internal_views(complete_signup_delivery),
    "get_signup_blocked_event_ids": _via_internal_views(get_signup_blocked_event_ids),
    "create_or_update_announcement": _create_or_update_announcement_orm,
    "get_repeater_subscribers": _get_repeater_subscribers_orm,
    "transition_event_state": _transition_event_state_orm,
}

# Modules that ``from app.internal_client import X`` at module level — the
# imported name lives on the importer's namespace, so patching only
# ``app.internal_client.X`` is not enough.
_CALLSITE_MODULES = (
    "app.internal_client.discord",
    "app.internal_client.events",
    "events.discord.embeds",
    "events.scheduling.fire",
    "events.tasks",
    "discordbot.utils",
)


class DiscordTestMixin:
    """TestCase mixin that swaps app.internal_client HTTP calls for ORM ones."""

    def setUp(self):
        super().setUp()
        self._patches = []
        for name, fn in _PATCH_MAP.items():
            p = patch(f"app.internal_client.{name}", fn)
            p.start()
            self._patches.append(p)

        for module_path in _CALLSITE_MODULES:
            try:
                module = importlib.import_module(module_path)
            except ImportError:
                continue
            for name, fn in _PATCH_MAP.items():
                if hasattr(module, name):
                    p = patch.object(module, name, fn)
                    p.start()
                    self._patches.append(p)

        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for p in self._patches:
            try:
                p.stop()
            except RuntimeError:
                # Already stopped
                pass
        self._patches = []
