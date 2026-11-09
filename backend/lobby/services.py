"""When a game gets a dota_lobby lobby, and what DraftForge asks dota_lobby for.

Runs in the Django process (it reads the ORM). Celery tasks reach it through
the internal API in lobby.views_internal.

A game is eligible for a lobby when all of these hold:

- DOTA_LOBBY_ENABLED is on and the tournament's `dota_lobby_mode` is not
  `off` (`auto` for automatic creation);
- the tournament is a Dota 2 tournament whose game mode dota_lobby can host
  (not "Custom Lobby");
- the game is `pending`, has both teams and has no active lobby;
- for automatic creation, the tournament is `in_progress`;
- every rostered player has a Steam account ID. A manual create may leave
  players without one out (`allow_missing`).

Sides start from the bracket slots: Game.radiant_team plays Radiant. The
teams actually sent are stored on the GameLobby, and only those are treated
as in-game sides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction

from app.models import DotaLobbyMode, Game, GameMode, GameType, Team
from lobby import broadcast, refs, states
from lobby.models import GameLobby
from lobby.passwords import derive_password

if TYPE_CHECKING:
    from app.models import CustomUser

MAX_TEAM_PLAYERS = 5
NAME_MAX_LENGTH = 64
TEAM_REF_PREFIX = "team-"
TV_DELAY_SECONDS = 120

# DraftForge game modes dota_lobby can host, by its mode names.
GAME_MODE_MAP = {
    GameMode.NORMAL: "ap",
    GameMode.CAPTAINS_MODE: "cm",
    GameMode.TURBO: "turbo",
}

# Lobby states in which the match has not started: the lobby can still be
# closed and recreated when the game's teams change.
PREGAME_STATES = frozenset(
    {
        states.REQUESTED,
        states.PENDING,
        states.CREATING,
        states.WAITING,
        states.READY,
    }
)
# dota_lobby flips teams only in these states.
FLIPPABLE_STATES = frozenset({states.WAITING, states.READY})

# A game whose latest lobby ended for one of these reasons gets a new one
# automatically. Any other ending (timed out, failed, refused) waits for an
# organizer to retry.
AUTO_RECREATE_REASONS = frozenset({"teams_changed"})
TEAMS_CHANGED = "teams_changed"
GAME_COMPLETED = "game_completed"

# How long one create attempt holds a `requested` row before the reconcile
# task may send it again. One attempt (three HTTP tries with their timeouts)
# fits well inside it.
CREATE_ATTEMPT_LEASE_SECONDS = 120


@dataclass(frozen=True)
class Eligibility:
    ok: bool
    code: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _fail(code: str, **details: Any) -> Eligibility:
    return Eligibility(False, code, details)


def is_enabled() -> bool:
    return bool(getattr(settings, "DOTA_LOBBY_ENABLED", False))


def external_ref_for(game_pk: int) -> str:
    return refs.build_external_ref(game_pk, settings.DOTA_LOBBY_REF_PREFIX)


def team_ref(team_pk: int) -> str:
    return f"{TEAM_REF_PREFIX}{team_pk}"


def parse_team_ref(ref: object) -> int | None:
    if not isinstance(ref, str) or not ref.startswith(TEAM_REF_PREFIX):
        return None
    tail = ref[len(TEAM_REF_PREFIX) :]
    return int(tail) if tail.isascii() and tail.isdigit() else None


def team_roster(team: Team) -> list[CustomUser]:
    """The team's members and its captain, by user pk."""
    users = {u.pk: u for u in team.members.all()}
    if team.captain_id and team.captain_id not in users:
        users[team.captain_id] = team.captain
    return [users[pk] for pk in sorted(users)]


def roster_players(team: Team) -> tuple[list[dict[str, Any]], list[int]]:
    """dota_lobby players for `team`, and the user pks without a Steam account."""
    players: list[dict[str, Any]] = []
    missing: list[int] = []
    for user in team_roster(team):
        if user.steam_account_id is None:
            missing.append(user.pk)
            continue
        player: dict[str, Any] = {"account_id": int(user.steam_account_id)}
        if user.pk == team.captain_id:
            player["captain"] = True
        players.append(player)
    return players, missing


def game_teams(game: Game) -> frozenset[int | None]:
    """The game's two teams, ignoring which slot each is in."""
    return frozenset({game.radiant_team_id, game.dire_team_id})


def lobby_teams(game_lobby: GameLobby) -> frozenset[int | None]:
    return frozenset({game_lobby.radiant_team_id, game_lobby.dire_team_id})


def active_lobby(game: Game) -> GameLobby | None:
    return game.lobbies.filter(ended=False).first()


def lobby_eligibility(
    game: Game, *, trigger: str = GameLobby.Trigger.AUTO, allow_missing: bool = False
) -> Eligibility:
    """Whether `game` may get a new lobby now, and why not."""
    if not is_enabled():
        return _fail("lobby_disabled")
    tournament = game.tournament
    if tournament is None:
        return _fail("no_tournament")
    if tournament.dota_lobby_mode == DotaLobbyMode.OFF:
        return _fail("lobby_mode_off")
    auto = trigger == GameLobby.Trigger.AUTO
    if auto and tournament.dota_lobby_mode != DotaLobbyMode.AUTO:
        return _fail("lobby_mode_manual")
    if tournament.game_type != GameType.DOTA2:
        return _fail("unsupported_game_type", game_type=tournament.game_type)
    if tournament.game_mode not in GAME_MODE_MAP:
        return _fail("unsupported_game_mode", game_mode=tournament.game_mode)
    if auto and tournament.state != "in_progress":
        return _fail("tournament_not_in_progress", state=tournament.state)
    if game.status != "pending":
        return _fail("game_not_pending", status=game.status)
    if not game.radiant_team_id or not game.dire_team_id:
        return _fail("teams_missing")
    if game.radiant_team_id == game.dire_team_id:
        return _fail("same_team")
    if game.lobbies.filter(ended=False).exists():
        return _fail("active_lobby_exists")
    if auto:
        latest = game.lobbies.order_by("-created_at", "-pk").first()
        if (
            latest is not None
            and latest.state_reason not in AUTO_RECREATE_REASONS
            and lobby_teams(latest) == game_teams(game)
        ):
            return _fail("lobby_already_requested", state=latest.state)

    missing: list[int] = []
    for team in (game.radiant_team, game.dire_team):
        players, team_missing = roster_players(team)
        missing.extend(team_missing)
        if len(players) > MAX_TEAM_PLAYERS:
            return _fail("team_too_large", team_id=team.pk, players=len(players))
    if missing and not (allow_missing and not auto):
        return _fail("missing_steam_ids", user_ids=missing)
    return Eligibility(True)


def auto_eligible_games() -> list[Game]:
    """Pending games that should get a lobby automatically and have none."""
    if not is_enabled():
        return []
    candidates = (
        Game.objects.filter(
            tournament__dota_lobby_mode=DotaLobbyMode.AUTO,
            tournament__state="in_progress",
            tournament__game_type=GameType.DOTA2,
            tournament__game_mode__in=list(GAME_MODE_MAP),
            status="pending",
            radiant_team__isnull=False,
            dire_team__isnull=False,
        )
        .exclude(lobbies__ended=False)
        .select_related("tournament", "radiant_team", "dire_team")
        .order_by("pk")
    )
    return [g for g in candidates if lobby_eligibility(g).ok]


def lobby_name(game: Game, radiant: Team, dire: Team) -> str:
    name = f"{game.tournament.name} R{game.round}: {radiant.name} vs {dire.name}"
    return name[:NAME_MAX_LENGTH]


def _league_id(game: Game) -> int | None:
    tournament = game.tournament
    league_id = tournament.lobby_steam_league_id or tournament.linked_steam_league_id
    return int(league_id) if league_id else None


def build_request(game: Game, game_lobby: GameLobby) -> dict[str, Any]:
    """The create body for `game_lobby`, without the password.

    Stored on the row, so every retry sends exactly the same request.
    """
    tournament = game.tournament
    radiant, dire = game.radiant_team, game.dire_team
    teams: dict[str, Any] = {}
    for side, team in (("radiant", radiant), ("dire", dire)):
        players, _missing = roster_players(team)
        teams[side] = {
            "team_ref": team_ref(team.pk),
            "name": team.name[:NAME_MAX_LENGTH],
            "players": players,
        }
    body: dict[str, Any] = {
        "external_ref": game_lobby.external_ref,
        "name": lobby_name(game, radiant, dire),
        "teams": teams,
        "game_mode": GAME_MODE_MAP[tournament.game_mode],
        "launch": tournament.dota_lobby_launch,
        "tv_delay_seconds": TV_DELAY_SECONDS,
        "kick_strangers": True,
        "metadata": {
            "draftforge_game_id": str(game.pk),
            "tournament_id": str(tournament.pk),
            "round": str(game.round),
            "game_lobby_id": str(game_lobby.pk),
        },
    }
    league_id = _league_id(game)
    if league_id:
        body["league_id"] = league_id
    region = tournament.dota_lobby_region or settings.DOTA_LOBBY_REGION
    if region:
        body["region"] = region
    return body


def create_body(game_lobby: GameLobby) -> dict[str, Any]:
    """The stored request plus the derived password: what Celery sends."""
    return {**game_lobby.request, "password": derive_password(game_lobby)}


@dataclass(frozen=True)
class Claim:
    game_lobby: GameLobby | None
    created: bool
    eligibility: Eligibility


def claim_lobby(
    game_pk: int,
    *,
    trigger: str = GameLobby.Trigger.AUTO,
    user_id: int | None = None,
    allow_missing: bool = False,
    game_lobby_id: int | None = None,
) -> Claim:
    """The game's active lobby, or a new `requested` row when it may have one.

    With `game_lobby_id` (a create retrying for a row it already holds) it
    is that row only, while it has not ended: a row an organizer closed is
    never replaced by the retry of its own create (`lobby_ended`).

    Locks the game, so two claims for one game never both create a row.
    """
    with transaction.atomic():
        game = (
            Game.objects.select_for_update()
            .select_related("tournament", "radiant_team", "dire_team")
            .get(pk=game_pk)
        )
        if game_lobby_id is not None:
            row = game.lobbies.filter(pk=game_lobby_id).first()
            if row is None or row.ended:
                return Claim(
                    None,
                    False,
                    _fail("lobby_ended", state=row.state if row else None),
                )
            return Claim(row, False, Eligibility(True))
        existing = active_lobby(game)
        if existing is not None:
            return Claim(existing, False, Eligibility(True))
        eligibility = lobby_eligibility(
            game, trigger=trigger, allow_missing=allow_missing
        )
        if not eligibility.ok:
            return Claim(None, False, eligibility)
        game_lobby = GameLobby.objects.create(
            game=game,
            external_ref=external_ref_for(game.pk),
            trigger=trigger,
            requested_by_id=user_id,
            radiant_team=game.radiant_team,
            dire_team=game.dire_team,
            league_id=_league_id(game),
        )
        game_lobby.request = build_request(game, game_lobby)
        game_lobby.save(update_fields=["request"])
        return Claim(game_lobby, True, eligibility)


def end_locally(game_lobby: GameLobby, reason: str) -> None:
    """Mark a lobby ended in DraftForge before dota_lobby has closed it.

    The caller closes it in dota_lobby. The row stops counting as the game's
    active lobby at once, so a replacement can be requested.
    """
    game_lobby.state = states.CLOSED
    game_lobby.state_reason = reason
    game_lobby.save(update_fields=["state", "state_reason", "updated_at"])


def desired_radiant_team_id(game: Game) -> int | None:
    """The team the completed hero draft put on Radiant, if there is one."""
    herodraft = getattr(game, "herodraft", None)
    if herodraft is None or herodraft.state != "completed":
        return None
    for draft_team in herodraft.draft_teams.all():
        if draft_team.is_radiant:
            return draft_team.tournament_team_id
    return None


def wants_flip(game_lobby: GameLobby) -> bool:
    """True when the hero draft's side choice contradicts the sides sent."""
    if game_lobby.state not in FLIPPABLE_STATES or not game_lobby.lobby_id:
        return False
    wanted = desired_radiant_team_id(game_lobby.game)
    if wanted is None or game_lobby.radiant_team_id is None:
        return False
    return wanted != game_lobby.radiant_team_id and wanted == game_lobby.dire_team_id


def queue_create(
    game: Game, *, user_id: int | None = None, allow_missing: bool = False
) -> Eligibility:
    """Manual create (organizer action): claim the row now, send it in Celery.

    The `requested` row exists before the task runs, and the task carries its
    ID through every retry. Closing the row therefore stops the create: the
    task's next claim answers `lobby_ended` instead of making a new row.
    """
    claim = claim_lobby(
        game.pk,
        trigger=GameLobby.Trigger.MANUAL,
        user_id=user_id,
        allow_missing=allow_missing,
    )
    if claim.game_lobby is None:
        return claim.eligibility
    if not claim.created:
        return _fail("active_lobby_exists", state=claim.game_lobby.state)
    from lobby.tasks import create_dota_lobby

    game_pk, pk = game.pk, claim.game_lobby.pk
    broadcast.lobby_changed_on_commit(claim.game_lobby, bracket_changed=False)
    transaction.on_commit(
        lambda: create_dota_lobby.delay(
            game_pk,
            trigger=GameLobby.Trigger.MANUAL,
            user_id=user_id,
            allow_missing=allow_missing,
            game_lobby_id=pk,
        )
    )
    return claim.eligibility


def close_lobby(game_lobby: GameLobby, reason: str) -> bool:
    """End a lobby that has not started and close it in dota_lobby.

    False when the match is already under way: dota_lobby ends such a lobby
    with the match.
    """
    if game_lobby.ended or game_lobby.state not in PREGAME_STATES:
        return False
    end_locally(game_lobby, reason)
    if game_lobby.lobby_id:
        from lobby.tasks import close_dota_lobby

        pk, lobby_id = game_lobby.pk, game_lobby.lobby_id
        transaction.on_commit(lambda: close_dota_lobby.delay(pk, lobby_id))
    return True
