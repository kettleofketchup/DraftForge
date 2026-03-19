"""
Discord message component builders (buttons, action rows).
"""

from django.conf import settings


def build_announcement_components(event):
    """Build action row components for event announcement message."""
    buttons = [
        {
            "type": 2,  # Button
            "style": 3,  # Success (green)
            "label": "Sign Up",
            "custom_id": f"event_signup:{event.pk}",
            "emoji": {"name": "\u2705"},
        },
        {
            "type": 2,  # Button
            "style": 4,  # Danger (red)
            "label": "Decline",
            "custom_id": f"event_decline:{event.pk}",
            "emoji": {"name": "\u274c"},
        },
    ]

    # Notify Me — only if event has a repeater
    if event.event_repeater_id:
        buttons.append(
            {
                "type": 2,
                "style": 2,  # Secondary (grey)
                "label": "Notify Me",
                "custom_id": f"event_notify:{event.pk}",
                "emoji": {"name": "\U0001f514"},
            }
        )

    # View Event — link button
    site_url = getattr(settings, "SITE_URL", "")
    if site_url:
        buttons.append(
            {
                "type": 2,
                "style": 5,  # Link
                "label": "View Event",
                "url": f"{site_url}/events/{event.pk}/",
                "emoji": {"name": "\U0001f517"},
            }
        )

    return [{"type": 1, "components": buttons}]  # Action Row
