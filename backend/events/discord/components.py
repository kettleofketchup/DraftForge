"""
Discord message component builders (buttons, action rows).
"""

from django.conf import settings


def build_announcement_components(event):
    """Build action row components for event announcement message.

    Row 1: Sign Up (green) | Tentative (grey) | Decline (grey + ❌)
    Row 2: Notify Me for Future Events (grey + 🔔) — only for repeater events
    """
    # Row 1: RSVP actions
    row1 = {
        "type": 1,
        "components": [
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
            {
                "type": 2,  # Button
                "style": 4,  # Danger (red)
                "label": "Decline",
                "custom_id": f"event_decline:{event.pk}",
                "emoji": {"name": "\U0001f1fd"},  # Regional indicator X
            },
        ],
    }

    rows = [row1]

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
