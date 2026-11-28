"""Celery tasks for tournament Discord notifications and auto-creation.

All data reads via internal_client HTTP calls (no ORM).
All DB writes via internal API POST/PATCH endpoints.
"""

from celery import Task, shared_task
from django.conf import settings

from app.internal_client import (
    create_activity_notification_invite,
    create_tournament_log,
    update_tournament_log,
)
from discordbot.dm import DELIVERED_OUTCOMES, DMRequest, send_dm, task_run_id
from discordbot.dm_keys import tournament_draft_link_key, tournament_herodraft_link_key
from discordbot.models import DMKind, DMSubject
from events.discord.tournament_embeds import (
    build_draft_link_components,
    build_draft_link_embed,
    build_herodraft_link_components,
    build_herodraft_link_embed,
)
from telemetry.logging import get_logger
from tournament.internal_client import (
    create_herodraft_for_game,
    get_auto_herodraft_games,
    get_match_participants,
    get_tournament_for_task,
    get_tournament_participants,
)

logger = get_logger(__name__)


def _fail_log_on_auth_error(
    tournament_log_id: int | None, sent: int, total: int, label: str
) -> None:
    if tournament_log_id:
        update_tournament_log(
            tournament_log_id,
            recipient_count=sent,
            message=(
                f"Stopped sending {label} after {sent}/{total}: "
                "Discord rejected the bot token"
            ),
            success=False,
        )


@shared_task(bind=True)
def send_tournament_draft_links(
    self: Task, tournament_id: int, draft_id: int | None
) -> str:
    """DM draft link to all tournament participants."""

    tournament = get_tournament_for_task(tournament_id)
    if not tournament:
        return f"Tournament {tournament_id} not found"
    if not tournament.discord_send_draft_link:
        return "Config disabled"

    invite_url = (
        create_activity_notification_invite("team", draft_id)
        if draft_id and settings.DISCORD_ACTIVITY_ENABLED
        else None
    )
    embed = build_draft_link_embed(
        tournament.name,
        tournament.draft_type,
        tournament_id,
        date_played=tournament.date_played,
        timezone=getattr(tournament, "timezone", None),
        one_click=invite_url is not None,
    )
    components = build_draft_link_components(
        tournament_id, draft_id=draft_id, invite_url=invite_url
    )
    participants = get_tournament_participants(tournament_id)

    # Create the parent log row first so child DiscordDM ledger rows can FK
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

    task_id = task_run_id(self)
    sent = 0
    failed_users = []
    for p in participants:
        outcome = send_dm(
            DMRequest(
                kind=DMKind.TOURNAMENT_DRAFT_LINK,
                idempotency_key=tournament_draft_link_key(
                    task_id=task_id, discord_id=p.discord_id
                ),
                discord_user_id=p.discord_id or None,
                recipient_user_id=p.user_pk,
                organization_id=tournament.organization_id,
                subject=(DMSubject.TOURNAMENT, tournament_id),
                tournament_log_id=tournament_log_id,
                context={"draft_id": draft_id, "activity": invite_url is not None},
                embed=embed,
                components=components,
            )
        )
        if outcome.auth_rejected:
            _fail_log_on_auth_error(
                tournament_log_id, sent, len(participants), "draft links"
            )
            return "Stopped: Discord rejected the bot token"
        if outcome.status in DELIVERED_OUTCOMES:
            sent += 1
        else:
            failed_users.append(p.username or p.discord_id)

    message = f"Sent draft link to {sent}/{len(participants)} participants"
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
        "tournament_draft_links_sent",
        system="events",
        subsystem="tasks",
        tournament_id=tournament_id,
        sent=sent,
        count=len(participants),
    )
    return message


@shared_task(bind=True)
def send_tournament_herodraft_links(
    self: Task,
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

    invite_url = (
        create_activity_notification_invite("hero", herodraft_id)
        if settings.DISCORD_ACTIVITY_ENABLED
        else None
    )
    embed = build_herodraft_link_embed(
        tournament.name,
        herodraft_id,
        radiant_name,
        dire_name,
        one_click=invite_url is not None,
    )
    components = build_herodraft_link_components(herodraft_id, invite_url=invite_url)
    participants = get_match_participants(game_id)

    # Create the parent log row first so child DiscordDM ledger rows can FK
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

    task_id = task_run_id(self)
    sent = 0
    failed_users = []
    for p in participants:
        outcome = send_dm(
            DMRequest(
                kind=DMKind.TOURNAMENT_HERODRAFT_LINK,
                idempotency_key=tournament_herodraft_link_key(
                    task_id=task_id, discord_id=p.discord_id
                ),
                discord_user_id=p.discord_id or None,
                recipient_user_id=p.user_pk,
                organization_id=tournament.organization_id,
                subject=(DMSubject.TOURNAMENT, tournament_id),
                tournament_log_id=tournament_log_id,
                context={
                    "draft_id": herodraft_id,
                    "game_id": game_id,
                    "activity": invite_url is not None,
                },
                embed=embed,
                components=components,
            )
        )
        if outcome.auth_rejected:
            _fail_log_on_auth_error(
                tournament_log_id, sent, len(participants), "hero draft links"
            )
            return "Stopped: Discord rejected the bot token"
        if outcome.status in DELIVERED_OUTCOMES:
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
