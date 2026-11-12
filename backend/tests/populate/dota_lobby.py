"""Populate and reset the dota_lobby E2E data (tests.data.dota_lobby).

populate_dota_lobby_data creates the org, league, series, events,
tournaments, teams and bracket games. reset_dota_lobby_data, behind
POST /api/tests/dota-lobby/reset/, puts the lobby state back between spec
files without recreating anything: it closes the lobbies the specs left in
dota_lobby, ends their rows, sets the games back to pending and restores the
password settings. seed_dota_lobby gives a game a lobby row without
dota_lobby, for specs that run where the simulator does not.
dota_lobby_test_data is the lookup the specs read.
"""

from __future__ import annotations

from datetime import time, timedelta
from typing import Any

from cacheops import invalidate_model, invalidate_obj
from django.db import transaction
from django.utils import timezone as tz

from app.models import (
    CustomUser,
    DotaLobbyMode,
    Game,
    GameMode,
    GameType,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from events.constants import EventState, RepeatFrequency, SignupStatus
from events.models import Event, EventRepeater, EventSignup
from events.services import (
    REPEATER_CREATE_COPY_FIELDS,
    create_tournament_for_event,
    push_lobby_password_to_tournament,
    sync_future_events,
    sync_tournament_from_event,
)
from lobby import services, states
from lobby.client import DotaLobbyClient, DotaLobbyError
from lobby.models import GameLobby
from lobby.passwords import PasswordMode, generate_password
from tests.data.dota_lobby import (
    LOBBY_FIXED_PASSWORD,
    LOBBY_LEAGUE,
    LOBBY_LEAGUE_STAFF_USER,
    LOBBY_LIFECYCLE_TEAMS,
    LOBBY_LIFECYCLE_TOURNAMENT_NAME,
    LOBBY_ORG,
    LOBBY_RANDOM_EVENT_NAME,
    LOBBY_RANDOM_TEAMS,
    LOBBY_RANDOM_TOURNAMENT_NAME,
    LOBBY_REGISTERED_USER,
    LOBBY_ROLE_USERS,
    LOBBY_SERIES_NAME,
    LOBBY_SERIES_TEAMS,
    LOBBY_SERIES_TOURNAMENT_NAME,
    LOBBY_STAFF_USER,
    LOBBY_TOURNAMENT_NAMES,
    LOBBY_USERS,
)
from tests.data.models import TestUser
from tests.dota_lobby_sim import SimulatorUnavailable, simulator_request
from tests.populate.utils import ensure_league_user, ensure_org_user

# The reason the reset writes on the lobby rows it ends.
RESET_REASON = "test_reset"
# The lobby ID prefix of seed_dota_lobby's rows: no dota_lobby holds them.
SEEDED_LOBBY_PREFIX = "lob_seeded_"
# What the reset puts the simulator's auto mode back to (simulator.yaml).
SIMULATOR_DEFAULTS = {
    "auto_join": True,
    "auto_join_delay_ms": 200,
    "auto_ready": True,
    "auto_start": True,
    "auto_start_delay_ms": 500,
}

_TOURNAMENT_DEFAULTS = {
    "tournament_type": "single_elimination",
    "game_type": GameType.DOTA2,
    "game_mode": GameMode.NORMAL,
    "draft_type": "shuffle",
    "people_per_team": 2,
    "timezone": LOBBY_ORG.timezone,
    "dota_lobby_mode": DotaLobbyMode.MANUAL,
}


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.steam_account_id = data.get_steam_account_id()
    user.save()  # computes steamid from steam_account_id
    return user


def _create_bracket(
    tournament: Tournament, teams: list[tuple[str, list[TestUser]]]
) -> list[Game]:
    """Teams with their players, and a single-elimination bracket for them."""
    team_rows = []
    for order, (name, players) in enumerate(teams, start=1):
        users = [CustomUser.objects.get(pk=p.pk) for p in players]
        team = Team.objects.create(
            tournament=tournament, name=name, captain=users[0], draft_order=order
        )
        team.members.set(users)
        team_rows.append(team)
    # add, not set(clear=True): clearing tournament.users empties (and so
    # deletes) its teams (app.signals.handle_tournament_user_removal).
    tournament.users.add(*(u for t in team_rows for u in t.members.all()))

    first_round = [
        Game.objects.create(
            tournament=tournament,
            round=1,
            bracket_type="winners",
            position=i // 2,
            elimination_type="single",
            radiant_team=team_rows[i],
            dire_team=team_rows[i + 1],
            status="pending",
        )
        for i in range(0, len(team_rows), 2)
    ]
    if len(first_round) == 2:
        final = Game.objects.create(
            tournament=tournament,
            round=2,
            bracket_type="winners",
            position=0,
            elimination_type="single",
            status="pending",
        )
        for game, slot in zip(first_round, ("radiant", "dire")):
            game.next_game = final
            game.next_game_slot = slot
            game.save(update_fields=["next_game", "next_game_slot"])
        return [*first_round, final]
    return first_round


def _delete_existing(org: Organization) -> None:
    # The tournaments go with their teams, games and lobby rows.
    Tournament.objects.filter(name__in=LOBBY_TOURNAMENT_NAMES).delete()
    Event.objects.filter(organization=org).delete()
    EventRepeater.objects.filter(organization=org).delete()


def populate_dota_lobby_data(force: bool = False) -> None:
    """Create the dota_lobby E2E org, league, series, events and tournaments."""
    print("  Populating dota_lobby E2E data...")
    org, _ = Organization.objects.update_or_create(
        name=LOBBY_ORG.name,
        defaults={"description": LOBBY_ORG.description, "timezone": LOBBY_ORG.timezone},
    )
    league, _ = League.objects.update_or_create(
        steam_league_id=LOBBY_LEAGUE.steam_league_id,
        defaults={"name": LOBBY_LEAGUE.name, "organization": org},
    )
    _delete_existing(org)

    users = {u.pk: _ensure_user(u) for u in LOBBY_USERS}
    for i, user in enumerate(users.values()):
        org_user = ensure_org_user(user, org, mmr=3000 + i * 50)
        ensure_league_user(user, org_user, league)

    staff = users[LOBBY_STAFF_USER.pk]
    org.admins.set([staff])
    invalidate_obj(org)
    # League staff only: may edit the tournaments, never sees the password.
    league_staff = users[LOBBY_LEAGUE_STAFF_USER.pk]
    league.staff.set([league_staff])
    invalidate_obj(league)

    scheduled = tz.now() + timedelta(days=3)
    # Paused, so the hourly generation never adds events to it; saving it
    # still cascades to its upcoming, on-schedule events.
    series = EventRepeater.objects.create(
        organization=org,
        name=LOBBY_SERIES_NAME,
        description="Series for the dota_lobby E2E tests.",
        frequency=RepeatFrequency.WEEKLY,
        day_of_week=scheduled.isoweekday() % 7,
        time_of_day=time(20, 0),
        starts_at=tz.now().date(),
        generate_days_ahead=7,
        is_active=False,
        created_by=staff,
        tournament_name=LOBBY_SERIES_TOURNAMENT_NAME,
        tournament_league=league,
        number_of_teams=4,
        auto_approve=True,
        max_players=8,
        dota_lobby_password_mode=PasswordMode.FIXED,
        dota_lobby_password=LOBBY_FIXED_PASSWORD,
        **_TOURNAMENT_DEFAULTS,
    )
    series_event = Event(
        organization=org,
        name=series.name,
        description=series.description,
        scheduled_at=scheduled,
        state=EventState.UPCOMING,
        created_by=staff,
        event_repeater=series,
    )
    for field_name in REPEATER_CREATE_COPY_FIELDS:
        setattr(series_event, field_name, getattr(series, field_name))
    series_event.dota_lobby_password = LOBBY_FIXED_PASSWORD
    series_event.tournament_date = scheduled
    series_event.save()
    series_tournament = create_tournament_for_event(series_event)
    _create_bracket(series_tournament, LOBBY_SERIES_TEAMS)
    EventSignup.objects.create(
        event=series_event,
        user=users[LOBBY_REGISTERED_USER.pk],
        status=SignupStatus.APPROVED,
    )

    random_event = Event.objects.create(
        organization=org,
        name=LOBBY_RANDOM_EVENT_NAME,
        description="One-off event with a random lobby password.",
        scheduled_at=scheduled,
        tournament_date=scheduled,
        state=EventState.UPCOMING,
        created_by=staff,
        tournament_name=LOBBY_RANDOM_TOURNAMENT_NAME,
        tournament_league=league,
        number_of_teams=2,
        auto_approve=True,
        max_players=4,
        dota_lobby_password_mode=PasswordMode.RANDOM,
        **_TOURNAMENT_DEFAULTS,
    )
    random_tournament = create_tournament_for_event(random_event)
    _create_bracket(random_tournament, LOBBY_RANDOM_TEAMS)

    lifecycle = Tournament.objects.create(
        name=LOBBY_LIFECYCLE_TOURNAMENT_NAME,
        league=league,
        date_played=tz.now(),
        state="in_progress",
        number_of_teams=2,
        **_TOURNAMENT_DEFAULTS,
    )
    _create_bracket(lifecycle, LOBBY_LIFECYCLE_TEAMS)

    print(
        f"    Created {org.name}, {league.name} (steam {league.steam_league_id}), "
        f"{series.name}, {random_event.name} and {lifecycle.name}"
    )


# ---------------------------------------------------------------------------
# Reset and lookup (backend/tests/test_dota_lobby.py)
# ---------------------------------------------------------------------------


def _org() -> Organization:
    return Organization.objects.nocache().get(name=LOBBY_ORG.name)


def _lobby_games() -> list[Game]:
    return list(
        Game.objects.nocache()
        .filter(tournament__name__in=LOBBY_TOURNAMENT_NAMES)
        .order_by("tournament_id", "round", "position")
    )


def _close_in_dota_lobby(rows: list[GameLobby]) -> None:
    """Best effort: close the lobbies the specs left open in dota_lobby."""
    open_rows = [
        r
        for r in rows
        if r.lobby_id
        and not r.lobby_id.startswith(SEEDED_LOBBY_PREFIX)
        and r.state not in states.SERVICE_TERMINAL_STATES
    ]
    if not open_rows:
        return
    try:
        client = DotaLobbyClient(backoff=())
    except DotaLobbyError:  # DOTA_LOBBY_URL is not set
        return
    for row in open_rows:
        try:
            client.close_lobby(row.lobby_id)
        except DotaLobbyError:
            continue


def _reset_simulator() -> None:
    """Best effort: the simulator's auto mode back to simulator.yaml."""
    try:
        simulator_request("PATCH", "/v1/sim/settings", json=SIMULATOR_DEFAULTS)
    except SimulatorUnavailable:
        return


@transaction.atomic
def _reset_rows_and_settings() -> None:
    games = _lobby_games()
    # Lobbies that ended before this reset are gone: a finished match would
    # otherwise block the next create (lobby_match_played). dota_lobby holds
    # a reference only while the lobby is active, so nothing points at them.
    GameLobby.objects.filter(game__in=games, ended=True).delete()
    rows = list(
        GameLobby.objects.select_for_update().filter(game__in=games, ended=False)
    )
    now = tz.now()
    for row in rows:
        # Kept, with their lobby ID, until the next reset: a create that
        # meets the lobby still closing in dota_lobby under the game's
        # reference closes it and retries (lobby.views_internal.conflict).
        row.state = states.CLOSED
        row.state_reason = RESET_REASON
        row.close_pending = False
        row.ended_at = now
        row.save()
    GameLobby.objects.filter(game__in=games, close_pending=True).update(
        close_pending=False
    )

    for game in games:
        game.status = "pending"
        game.winning_team = None
        game.gameid = None
        game.save(update_fields=["status", "winning_team", "gameid"])

    org = _org()
    series = EventRepeater.objects.nocache().get(
        organization=org, name=LOBBY_SERIES_NAME
    )
    series.dota_lobby_mode = DotaLobbyMode.MANUAL
    series.dota_lobby_password_mode = PasswordMode.FIXED
    series.dota_lobby_password = LOBBY_FIXED_PASSWORD
    series.save()
    for event in sync_future_events(series):
        invalidate_obj(event)

    random_event = Event.objects.nocache().get(
        organization=org, name=LOBBY_RANDOM_EVENT_NAME
    )
    random_event.dota_lobby_mode = DotaLobbyMode.MANUAL
    random_event.dota_lobby_password_mode = PasswordMode.RANDOM
    random_event.dota_lobby_password = generate_password()
    random_event.save()
    sync_tournament_from_event(random_event)
    push_lobby_password_to_tournament(random_event)
    invalidate_obj(random_event)

    Tournament.objects.filter(name=LOBBY_LIFECYCLE_TOURNAMENT_NAME).update(
        state="in_progress", dota_lobby_mode=DotaLobbyMode.MANUAL
    )
    invalidate_model(Tournament)
    invalidate_model(Game)


def reset_dota_lobby_data() -> dict[str, Any]:
    """Put the lobby state back to the populated baseline; returns the lookup."""
    rows = list(
        GameLobby.objects.filter(game__in=_lobby_games(), ended=False).only(
            "pk", "lobby_id", "state"
        )
    )
    _close_in_dota_lobby(rows)
    _reset_simulator()
    _reset_rows_and_settings()
    return dota_lobby_test_data()


class SeedRefused(Exception):
    """The game cannot have a lobby now (an eligibility code), or is not a lobby test game."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def seed_dota_lobby(game_pk: int) -> GameLobby:
    """A `waiting` lobby row for a lobby test game, as if dota_lobby created it.

    Nothing is sent to dota_lobby: the row is claimed as a staff create would
    claim it (the event's password, the rostered teams) and marked accepted
    under a lobby ID no dota_lobby holds. For specs that check what
    DraftForge shows of a lobby where no simulator runs. Only for stacks
    without one: the reconcile task would find the lobby missing there and
    end the row. A game that already has an active lobby keeps it.
    """
    if game_pk not in {g.pk for g in _lobby_games()}:
        raise SeedRefused("not_a_lobby_test_game")
    claim = services.claim_lobby(game_pk, trigger=GameLobby.Trigger.MANUAL)
    row = claim.game_lobby
    if row is None:
        raise SeedRefused(claim.eligibility.code or "not_eligible")
    if claim.created:
        row.lobby_id = f"{SEEDED_LOBBY_PREFIX}{row.pk}"
        row.state = states.WAITING
        row.bot = "seeded"
        row.league_verified = True
        row.accepted_at = tz.now()
        row.save()
    return row


def _games_payload(tournament: Tournament) -> list[dict[str, Any]]:
    return [
        {
            "pk": g.pk,
            "round": g.round,
            "position": g.position,
            "bracket_type": g.bracket_type,
            "radiant_team": g.radiant_team.name if g.radiant_team else None,
            "dire_team": g.dire_team.name if g.dire_team else None,
            "status": g.status,
        }
        for g in tournament.games.nocache()
        .select_related("radiant_team", "dire_team")
        .order_by("round", "position")
    ]


def _players_payload(tournament: Tournament) -> dict[str, list[dict[str, Any]]]:
    return {
        team.name: [
            {"pk": u.pk, "username": u.username, "account_id": u.steam_account_id}
            for u in team.members.nocache().order_by("pk")
        ]
        for team in Team.objects.nocache()
        .filter(tournament=tournament)
        .order_by("draft_order")
    }


def dota_lobby_test_data() -> dict[str, Any]:
    """PKs, names and passwords the specs look up (never hardcoded there)."""
    org = _org()
    league = League.objects.nocache().get(steam_league_id=LOBBY_LEAGUE.steam_league_id)
    series = EventRepeater.objects.nocache().get(
        organization=org, name=LOBBY_SERIES_NAME
    )
    series_event = Event.objects.nocache().get(
        event_repeater=series, is_off_schedule=False
    )
    random_event = Event.objects.nocache().get(
        organization=org, name=LOBBY_RANDOM_EVENT_NAME
    )
    lifecycle = Tournament.objects.nocache().get(name=LOBBY_LIFECYCLE_TOURNAMENT_NAME)

    def tournament_payload(tournament: Tournament) -> dict[str, Any]:
        return {
            "pk": tournament.pk,
            "name": tournament.name,
            "games": _games_payload(tournament),
            "teams": _players_payload(tournament),
        }

    return {
        "org": {"pk": org.pk, "name": org.name},
        "league": {
            "pk": league.pk,
            "name": league.name,
            "steam_league_id": league.steam_league_id,
        },
        "fixed_password": LOBBY_FIXED_PASSWORD,
        "series": {"pk": series.pk, "name": series.name},
        "series_event": {
            "pk": series_event.pk,
            "name": series_event.name,
            "tournament": tournament_payload(series_event.tournament),
        },
        "random_event": {
            "pk": random_event.pk,
            "name": random_event.name,
            "tournament": tournament_payload(random_event.tournament),
        },
        "lifecycle_tournament": tournament_payload(lifecycle),
        "users": {
            role: {"pk": user.pk, "username": user.username}
            for role, user in LOBBY_ROLE_USERS.items()
        },
    }
