"""Events: state transitions, event reads, repeaters and due scheduled events."""

from typing import TYPE_CHECKING, Any

import requests

from app.internal_client import transport
from events.schemas import (
    EventSignupSchema,
    EventTaskSchema,
    RepeaterSubscriberSchema,
    ScheduledEventDueSchema,
)

if TYPE_CHECKING:
    from events.schemas import (
        EventSignupSchema,
        EventTaskSchema,
        RepeaterSubscriberSchema,
        ScheduledEventDueSchema,
    )


# ---- Writes ----


def transition_event_state(event_pk: int, new_state: str) -> requests.Response | None:
    """Transition event to a new state."""
    return transport.post(f"/events/{event_pk}/transition/", {"state": new_state})


def auto_close_event(event_pk: int) -> dict | None:
    resp = transport.post(f"/events/{event_pk}/auto-close/", {})
    if resp is not None and resp.ok:
        return resp.json()
    return None


# ---- Reads (public API; internal token accepted globally) ----


def get_event(pk: int) -> requests.Response | None:
    """Get event data by PK via public API."""
    return transport.api_get(f"/events/{pk}/")


def get_event_signups(event_id: int) -> list["EventSignupSchema"]:
    """Get signup list for an event via public API.

    Raises InternalAPIUnavailable on a network or HTTP error, so a failed
    read is never mistaken for an event with no signups.
    """

    resp = transport.api_get("/events/signups/", params={"event": event_id})
    if resp is None or not resp.ok:
        status = resp.status_code if resp is not None else None
        raise transport.InternalAPIUnavailable(
            f"signup list for event {event_id} unavailable (status={status})"
        )
    return [EventSignupSchema.model_validate(s) for s in resp.json()]


def get_events_list(**params: Any) -> list[dict[str, Any]]:
    """Get events list via public API with query params.

    Returns list of dicts (slim serializer output).
    Example: get_events_list(states="upcoming,signups_open", scheduled_before="2026-01-01T00:00:00Z")
    """
    resp = transport.api_get("/events/", params=params)
    if resp and resp.ok:
        return resp.json()
    return []


def get_events(params: dict[str, Any] | None = None) -> requests.Response | None:
    """List events with filters via public API."""
    return transport.api_get("/events/", params=params)


def get_event_for_task(pk: int) -> "EventTaskSchema | None":
    """Get full event data + org Discord config for celery tasks.

    Returns EventTaskData (Pydantic) with typed attribute access,
    or None if event not found / API error.
    """

    resp = transport.get(f"/events/{pk}/full/")
    if resp and resp.ok:
        return EventTaskSchema.model_validate(resp.json())
    return None


# ---- Repeaters and scheduled events ----


def get_active_repeaters() -> list[dict[str, Any]]:
    """Get all active repeaters via internal API."""
    resp = transport.get("/repeaters/active/")
    if resp and resp.ok:
        return resp.json()
    return []


def generate_repeater_events(repeater_pk: int) -> int:
    """Trigger event generation for a specific repeater. Returns created count."""
    resp = transport.post(f"/repeaters/{repeater_pk}/generate/", {})
    if resp and resp.ok:
        return resp.json().get("created_count", 0)
    return 0


def get_repeater_subscribers(repeater_id: int) -> list["RepeaterSubscriberSchema"]:
    """Get subscribers for a repeater. Returns list of RepeaterSubscriber."""

    resp = transport.get(f"/repeaters/{repeater_id}/subscribers/")
    if resp and resp.ok:
        return [RepeaterSubscriberSchema.model_validate(s) for s in resp.json()]
    return []


def get_due_scheduled_events() -> list["ScheduledEventDueSchema"]:
    """Get ScheduledEvents due for posting. Returns list of ScheduledEventDue."""

    resp = transport.get("/scheduled-events/due/")
    if resp and resp.ok:
        return [ScheduledEventDueSchema.model_validate(e) for e in resp.json()]
    return []
