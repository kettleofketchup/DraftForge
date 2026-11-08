"""Team-draft tick driver entry points (driver filled in a later task)."""

from typing import Any

from django.db import transaction

from app.tasks import draft_tick

TEAM_TICK_DRIVER: Any = None


def start_team_tick_broadcaster_after_commit(draft_id: int) -> None:
    transaction.on_commit(
        lambda: draft_tick.start_tick_broadcaster(TEAM_TICK_DRIVER, draft_id)
    )
