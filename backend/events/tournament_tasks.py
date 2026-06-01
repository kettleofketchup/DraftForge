"""Celery tasks for tournament Discord notifications and auto-creation.

All data reads via internal_client HTTP calls (no ORM).
All DB writes via internal API POST/PATCH endpoints.
"""

from celery import shared_task

from telemetry.logging import get_logger

logger = get_logger(__name__)


@shared_task
def send_tournament_draft_links(tournament_id, draft_id):
    """DM draft link to all tournament participants."""
    from app.internal_client import (
        create_tournament_log,
        get_tournament_for_task,
        get_tournament_participants,
    )
    from discordbot.utils import sync_send_dm
    from events.discord.tournament_embeds import (
        build_draft_link_components,
        build_draft_link_embed,
    )

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
    components = build_draft_link_components(tournament_id)
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
        from app.internal_client import update_tournament_log

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
    tournament_id, herodraft_id, game_id, radiant_name="", dire_name=""
):
    """DM hero draft link to match players."""
    from app.internal_client import (
        create_tournament_log,
        get_match_participants,
        get_tournament_for_task,
    )
    from discordbot.utils import sync_send_dm
    from events.discord.tournament_embeds import (
        build_herodraft_link_components,
        build_herodraft_link_embed,
    )

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
        from app.internal_client import update_tournament_log

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
def auto_create_herodrafts(tournament_id):
    """Poll for matches needing hero drafts. Self-reschedules every 10s.

    Reads via internal API. Creates hero drafts via internal API
    (Django endpoint handles select_for_update atomicity).
    """
    from app.internal_client import (
        create_herodraft_for_game,
        get_games_without_herodraft,
        get_tournament_for_task,
    )

    tournament = get_tournament_for_task(tournament_id)
    if not tournament:
        return f"Tournament {tournament_id} not found"

    if tournament.state == "past":
        logger.info(
            "tournament_auto_create_stopped",
            system="events",
            subsystem="tasks",
            tournament_id=tournament_id,
            reason="tournament_completed",
        )
        return "Tournament completed"

    if not tournament.auto_create_hero_drafts:
        logger.info(
            "tournament_auto_create_skipped",
            system="events",
            subsystem="tasks",
            tournament_id=tournament_id,
            reason="config_disabled",
        )
        return "Config disabled"

    games = get_games_without_herodraft(tournament_id)
    created_count = 0

    for game in games:
        if not game.has_captains:
            continue

        resp = create_herodraft_for_game(game.id)
        if not resp or not resp.ok:
            logger.error(
                "herodraft_create_failed",
                system="events",
                subsystem="tasks",
                tournament_id=tournament_id,
                game_id=game.id,
            )
            continue

        result = resp.json()
        if result.get("created"):
            created_count += 1
            herodraft_pk = result["id"]

            if tournament.discord_send_herodraft_link:
                send_tournament_herodraft_links.delay(
                    tournament_id,
                    herodraft_pk,
                    game.id,
                    radiant_name=game.radiant_team_name,
                    dire_name=game.dire_team_name,
                )

    if created_count > 0:
        logger.info(
            "herodrafts_auto_created",
            system="events",
            subsystem="tasks",
            tournament_id=tournament_id,
            count=created_count,
        )

    auto_create_herodrafts.apply_async(args=[tournament_id], countdown=10)
    return f"Created {created_count} hero drafts"
