"""Lobby triggers: game saves and hero draft completion.

- A game that becomes eligible (both teams set, tournament in `auto` mode,
  see lobby.services) gets a create task once the save commits. The
  reconcile task's sweep catches anything this misses.
- When a game's teams change while its lobby has not started, the lobby is
  ended here and closed in dota_lobby, and a new one is requested for the new
  teams, so a lobby's roster always matches the bracket.
- When a game is completed (or gets a winner) while its lobby has not
  started, for example a forfeit decided with advance-winner, the lobby is
  ended and closed so it does not hold a bot.
- A deleted game's lobby is closed in dota_lobby before the row goes with it.
- When a hero draft completes with the other side choice than the lobby was
  created with, the lobby's teams are flipped.

Nothing here runs while DOTA_LOBBY_ENABLED is off.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from app.models import Game, HeroDraft
from lobby import broadcast, services
from lobby.models import GameLobby
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "signals"}


def _close_for_team_change(game_lobby: GameLobby) -> None:
    services.close_lobby(game_lobby, services.TEAMS_CHANGED)
    log.info(
        "lobby_closed_teams_changed",
        game_id=game_lobby.game_id,
        game_lobby_id=game_lobby.pk,
        lobby_id=game_lobby.lobby_id,
        **_LOG,
    )
    broadcast.lobby_changed_on_commit(game_lobby, bracket_changed=False)


def _close_for_game_completed(game_lobby: GameLobby) -> None:
    services.close_lobby(game_lobby, services.GAME_COMPLETED)
    log.info(
        "lobby_closed_game_completed",
        game_id=game_lobby.game_id,
        game_lobby_id=game_lobby.pk,
        lobby_id=game_lobby.lobby_id,
        **_LOG,
    )
    broadcast.lobby_changed_on_commit(game_lobby, bracket_changed=False)


@receiver(post_save, sender="app.Game", dispatch_uid="lobby_game_saved")
def lobby_on_game_saved(
    sender: type, instance: Game, raw: bool = False, **kwargs: object
) -> None:
    if raw or not services.is_enabled() or not instance.tournament_id:
        return
    game = instance
    with transaction.atomic():
        current = (
            GameLobby.objects.select_for_update()
            .filter(game_id=game.pk, ended=False)
            .first()
        )
        if current is not None and services.lobby_teams(current) != services.game_teams(
            game
        ):
            if current.state in services.PREGAME_STATES:
                _close_for_team_change(current)
                current = None
            else:
                log.warning(
                    "lobby_teams_changed_in_game",
                    game_id=game.pk,
                    game_lobby_id=current.pk,
                    state=current.state,
                    **_LOG,
                )
        if (
            current is not None
            and current.state in services.PREGAME_STATES
            and (game.status == "completed" or game.winning_team_id is not None)
        ):
            # Decided without the lobby's match: nobody will play in it.
            _close_for_game_completed(current)
            return
        if current is not None:
            return
        if not (
            game.radiant_team_id and game.dire_team_id and game.status == "pending"
        ):
            return
        if not services.lobby_eligibility(game).ok:
            return

    from lobby.tasks import create_dota_lobby

    game_pk = game.pk
    log.info("lobby_auto_create_queued", game_id=game_pk, **_LOG)
    transaction.on_commit(lambda: create_dota_lobby.delay(game_pk, trigger="auto"))


@receiver(post_save, sender="app.HeroDraft", dispatch_uid="lobby_herodraft_saved")
def lobby_on_herodraft_saved(
    sender: type, instance: HeroDraft, raw: bool = False, **kwargs: object
) -> None:
    if raw or not services.is_enabled() or instance.state != "completed":
        return
    game_lobby = (
        GameLobby.objects.select_related("game")
        .filter(game_id=instance.game_id, ended=False)
        .first()
    )
    if game_lobby is None or not services.wants_flip(game_lobby):
        return

    from lobby.tasks import flip_lobby_sides

    pk, lobby_id = game_lobby.pk, game_lobby.lobby_id
    radiant_ref = services.team_ref(game_lobby.dire_team_id)
    log.info("lobby_flip_queued", game_id=instance.game_id, game_lobby_id=pk, **_LOG)
    transaction.on_commit(lambda: flip_lobby_sides.delay(pk, lobby_id, radiant_ref))


@receiver(pre_delete, sender="app.Game", dispatch_uid="lobby_game_deleted")
def lobby_on_game_deleted(sender: type, instance: Game, **kwargs: object) -> None:
    """Close the deleted game's lobby, which would otherwise hold a bot."""
    if not services.is_enabled():
        return
    from lobby.tasks import close_dota_lobby

    for row in GameLobby.objects.filter(
        game_id=instance.pk,
        ended=False,
        lobby_id__isnull=False,
        state__in=services.PREGAME_STATES,
    ):
        pk, lobby_id = row.pk, row.lobby_id
        log.info(
            "lobby_closed_game_deleted", game_id=instance.pk, lobby_id=lobby_id, **_LOG
        )
        transaction.on_commit(
            lambda pk=pk, lobby_id=lobby_id: close_dota_lobby.delay(pk, lobby_id)
        )
