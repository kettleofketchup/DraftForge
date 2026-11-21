"""Celery tasks for tournament Discord notifications and auto-creation.

All data reads via internal_client HTTP calls (no ORM).
All DB writes via internal API POST/PATCH endpoints.
"""

from celery import shared_task

from app.internal_client import (
    create_herodraft_for_game,
    create_tournament_log,
    get_auto_herodraft_games,
    get_match_participants,
    get_tournament_for_task,
    get_tournament_participants,
    update_tournament_log,
)
from discordbot.utils import sync_send_dm
from events.discord.tournament_embeds import (
    build_draft_link_components,
    build_draft_link_embed,
    build_herodraft_link_components,
    build_herodraft_link_embed,
)
from telemetry.logging import get_logger

logger = get_logger(__name__)


@shared_task
def send_tournament_draft_links(tournament_id: int, draft_id: int) -> str:
    """DM draft link to all tournament participants."""

    tournament = get_tournament_for_task(tournament_id)
    if not tournament:
        return f"Tournament {tournament_id} not found"
    if not tournament.discord_send_draft_link:
        return "Config disabled"

    embed = build_draft_link_embed(
        tournament.name,
        tournament.draft_type,
        tournament_id,
        date_played=tournament.date_played,
        timezone=getattr(tournament, "timezone", None),
    )
    components = build_draft_link_components(tournament_id, draft_id=draft_id)
    participants = get_tournament_participants(tournament_id)

    # Create the parent log row first so child DiscordMessageLog rows can FK
    # to it. success=None marks the row as in-flight; the post-loop
    # update_tournament_log call below flips it to True/False with the final
    # count. Consumers polling this row MUST wait for a terminal state.
    log_resp = create_tournament_log(
        tournament_id=tournament_id,
        category="notification",
        notification_type="draft_link",
        message=f"Sending draft link to {len(participants)} participants...",
        recipient_count=0,
        success=None,
    )
    tournament_log_id = log_resp.json().get("id") if log_resp and log_resp.ok else None

    sent = 0
    failed_users = []
    for p in participants:
        result = sync_send_dm(
            p.discord_id,
            embed=embed,
            components=components,
            tournament_log_id=tournament_log_id,
        )
        if result:
            sent += 1
        else:
            failed_users.append(p.username or p.discord_id)

    message = f"Sent draft link to {sent}/{len(participants)} participants"
    if failed_users:
        message += f". Failed: {', '.join(failed_users[:10])}"

    # Flip the in-flight row to its terminal state with the actual count.
    if tournament_log_id:
        update_tournament_log(
            tournament_log_id,
            recipient_count=sent,
            message=message,
            success=sent > 0,
        )

    logger.info(
        "tournament_draft_links_sent",
        system="events",
        subsystem="tasks",
        tournament_id=tournament_id,
        sent=sent,
        count=len(participants),
    )
    return message


@shared_task
def send_tournament_herodraft_links(
    tournament_id: int,
    herodraft_id: int,
    game_id: int,
    radiant_name: str = "",
    dire_name: str = "",
) -> str:
    """DM hero draft link to match players."""

    tournament = get_tournament_for_task(tournament_id)
    if not tournament:
        return f"Tournament {tournament_id} not found"
    if not tournament.discord_send_herodraft_link:
        return "Config disabled"

    embed = build_herodraft_link_embed(
        tournament.name, herodraft_id, radiant_name, dire_name
    )
    components = build_herodraft_link_components(herodraft_id)
    participants = get_match_participants(game_id)

    # Create the parent log row first so child DiscordMessageLog rows can FK
    # to it. success=None = in-flight; flipped by update_tournament_log below.
    team_names = f"{radiant_name} vs {dire_name}"
    log_resp = create_tournament_log(
        tournament_id=tournament_id,
        category="notification",
        notification_type="herodraft_link",
        message=f"Sending hero draft link to {len(participants)} players ({team_names})...",
        recipient_count=0,
        success=None,
    )
    tournament_log_id = log_resp.json().get("id") if log_resp and log_resp.ok else None

    sent = 0
    failed_users = []
    for p in participants:
        result = sync_send_dm(
            p.discord_id,
            embed=embed,
            components=components,
            tournament_log_id=tournament_log_id,
        )
        if result:
            sent += 1
        else:
            failed_users.append(p.username or p.discord_id)

    message = (
        f"Sent hero draft link to {sent}/{len(participants)} players ({team_names})"
    )
    if failed_users:
        message += f". Failed: {', '.join(failed_users[:10])}"

    if tournament_log_id:
        update_tournament_log(
            tournament_log_id,
            recipient_count=sent,
            message=message,
            success=sent > 0,
        )

    logger.info(
        "tournament_herodraft_links_sent",
        system="events",
        subsystem="tasks",
        tournament_id=tournament_id,
        sent=sent,
        count=len(participants),
    )
    return message


@shared_task
def sweep_auto_herodrafts() -> str:
    """Create hero drafts for every game that is ready, in every tournament
    with auto_create_hero_drafts on. Runs on the beat schedule."""

    created_count = 0
    for game in get_auto_herodraft_games():
        resp = create_herodraft_for_game(game.id)
        if not resp or not resp.ok:
            logger.error(
                "herodraft_create_failed",
                system="events",
                subsystem="tasks",
                tournament_id=game.tournament_id,
                game_id=game.id,
            )
            continue

        result = resp.json()
        if not result.get("created"):
            continue
        created_count += 1
        logger.info(
            "herodraft_auto_created",
            system="events",
            subsystem="tasks",
            tournament_id=game.tournament_id,
            game_id=game.id,
            herodraft_id=result["id"],
        )
        if game.discord_send_herodraft_link:
            send_tournament_herodraft_links.delay(
                game.tournament_id,
                result["id"],
                game.id,
                radiant_name=game.radiant_team_name,
                dire_name=game.dire_team_name,
            )

    return f"Created {created_count} hero drafts"


@shared_task
def auto_create_herodrafts(tournament_id: int) -> str:
    """Retired per-tournament polling loop; sweep_auto_herodrafts replaced it.

    Kept registered so loop messages still queued from before the deploy are
    consumed instead of erroring as unregistered.
    """
    return "Replaced by sweep_auto_herodrafts"
