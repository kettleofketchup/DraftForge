"""
Discord message component builders (buttons, action rows).
"""

from typing import TYPE_CHECKING, Any

from events.admission import decline_offered, self_serve_offered

if TYPE_CHECKING:
    from events.models import Event
    from events.schemas import EventTaskSchema


def build_announcement_components(
    event: "Event | EventTaskSchema",
) -> list[dict[str, Any]]:
    """Build action row components for event announcement message.

    Row 1: Sign Up (green) | Tentative (grey) | Decline (grey + ❌). Sign Up and
    Tentative show only while self-serve signups are accepted; Decline shows
    until the event starts. The row is dropped when it would be empty.
    Row 2: Notify Me for Future Events (grey + 🔔) — only for repeater events
    """
    self_serve = [
        {
            "type": 2,  # Button
            "style": 3,  # Success (green)
            "label": "Sign Up",
            "custom_id": f"event_signup:{event.pk}",
            "emoji": {"name": "\u2705"},
        },
        {
            "type": 2,  # Button
            "style": 1,  # Primary (blue)
            "label": "Tentative",
            "custom_id": f"event_tentative:{event.pk}",
            "emoji": {"name": "\u2753"},
        },
    ]
    decline = {
        "type": 2,  # Button
        "style": 4,  # Danger (red)
        "label": "Decline",
        "custom_id": f"event_decline:{event.pk}",
        "emoji": {"name": "\U0001f1fd"},  # Regional indicator X
    }
    rsvp_actions = [
        *(self_serve if self_serve_offered(event) else []),
        *([decline] if decline_offered(event) else []),
    ]
    rows = [{"type": 1, "components": rsvp_actions}] if rsvp_actions else []

    # Row 2: Notify Me — only if event has a repeater
    if event.event_repeater_id:
        row2 = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,  # Secondary (grey)
                    "label": "Notify Me for Future Events",
                    "custom_id": f"event_notify:{event.pk}",
                    "emoji": {"name": "\U0001f514"},
                },
            ],
        }
        rows.append(row2)

    return rows
