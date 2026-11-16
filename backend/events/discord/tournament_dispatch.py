"""Dispatch functions for tournament Discord notifications.

These run in Django (same process), so they CAN access ORM.
They check config flags and fire Celery tasks via .delay().
"""

from telemetry.logging import get_logger

logger = get_logger(__name__)


def notify_draft_started(tournament, draft):
    """Dispatch DM task if discord_send_draft_link is enabled."""
    if not tournament.discord_send_draft_link:
        return
    from events.tournament_tasks import send_tournament_draft_links

    send_tournament_draft_links.delay(tournament.pk, draft.pk)
    logger.info(
        "draft_links_dispatched",
        system="events",
        subsystem="dispatch",
        tournament_id=tournament.pk,
    )


def notify_herodraft_created(tournament, herodraft, game):
    """Dispatch DM task if discord_send_herodraft_link is enabled."""
    if not tournament.discord_send_herodraft_link:
        return
    from events.tournament_tasks import send_tournament_herodraft_links

    send_tournament_herodraft_links.delay(
        tournament.pk,
        herodraft.pk,
        game.pk,
        radiant_name=game.radiant_team.name if game.radiant_team else "",
        dire_name=game.dire_team.name if game.dire_team else "",
    )
    logger.info(
        "herodraft_links_dispatched",
        system="events",
        subsystem="dispatch",
        tournament_id=tournament.pk,
    )
