"""Populate the per-game org MMR E2E data (tests.data.game_org_mmr).

populate_game_org_mmr_data creates org/league 50, users 8000-8007 with both
games' org MMRs, the Dota tournament and the Deadlock event + tournament.
reset_game_org_mmr_approve, behind POST /api/tests/game-org-mmr/approve-setup/,
rebuilds the Deadlock approve event with a pending signup for 8007.
game_org_mmr_test_data is the lookup the specs read.
"""

from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser
from common.game import GameType
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.services import create_tournament_for_event
from league.models import League
from org.mmr import set_org_mmr
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDeadlockProfile
from tests.data.game_org_mmr import (
    GAME_MMR_APPROVE_DOTA,
    GAME_MMR_APPROVE_EVENT_NAME,
    GAME_MMR_APPROVE_RANK,
    GAME_MMR_APPROVE_TOURNAMENT_NAME,
    GAME_MMR_APPROVE_USER,
    GAME_MMR_DEADLOCK_EVENT_NAME,
    GAME_MMR_DEADLOCK_TOURNAMENT_NAME,
    GAME_MMR_DISPLAY_USER,
    GAME_MMR_DOTA_TOURNAMENT_NAME,
    GAME_MMR_EDIT_USER,
    GAME_MMR_LEAGUE,
    GAME_MMR_ORG,
    GAME_MMR_PLAYERS,
    GAME_MMR_TOURNAMENT_USERS,
)
from tests.data.models import TestUser
from tests.populate.utils import ensure_org_user
from tournament.models import Tournament
from user.models import PositionsModel

_APPROVE_RANK_DATE = date(2026, 1, 15)


def _ensure_org_and_league() -> tuple[Organization, League]:
    org, _ = Organization.objects.update_or_create(
        pk=GAME_MMR_ORG.pk,
        defaults={
            "name": GAME_MMR_ORG.name,
            "description": GAME_MMR_ORG.description,
            "logo": "",
            "timezone": GAME_MMR_ORG.timezone,
        },
    )
    league, _ = League.objects.update_or_create(
        pk=GAME_MMR_LEAGUE.pk,
        defaults={
            "steam_league_id": GAME_MMR_LEAGUE.steam_league_id,
            "name": GAME_MMR_LEAGUE.name,
            "organization": org,
            "timezone": GAME_MMR_LEAGUE.timezone,
        },
    )
    return org, league


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.save()
    return user


def _ensure_deadlock_rank(org_user: OrgUser) -> None:
    PlayerDeadlockProfile.objects.update_or_create(
        org_user=org_user,
        defaults={"rank": GAME_MMR_APPROVE_RANK, "rank_date": _APPROVE_RANK_DATE},
    )


def _deadlock_event(
    org: Organization,
    league: League,
    name: str,
    tournament_name: str,
    state: str,
) -> Event:
    start = timezone.now() + timedelta(days=7)
    event = Event.objects.create(
        organization=org,
        name=name,
        description="Deadlock event for the per-game org MMR E2E tests.",
        scheduled_at=start,
        ends_at=start + timedelta(hours=3),
        state=state,
        game_type=GameType.DEADLOCK,
        tournament_name=tournament_name,
        tournament_league=league,
    )
    create_tournament_for_event(event)
    event.refresh_from_db()
    return event


def _delete_events(org: Organization, event_name: str, tournament_name: str) -> None:
    Event.objects.nocache().filter(organization=org, name=event_name).delete()
    Tournament.objects.nocache().filter(
        league__organization=org, name=tournament_name
    ).delete()


@transaction.atomic
def populate_game_org_mmr_data(force: bool = False) -> None:
    """Create the per-game org MMR org, users, ratings and tournaments.

    Users and ratings are updated in place. `force` rebuilds the tournaments
    and the Deadlock event.
    """
    print("  Populating per-game org MMR E2E data...")
    org, league = _ensure_org_and_league()
    tournament_user_pks = [u.pk for u in GAME_MMR_TOURNAMENT_USERS]
    for player in GAME_MMR_PLAYERS:
        user = _ensure_user(player.user)
        org_user = ensure_org_user(
            user,
            org,
            mmr=player.dota,
            game_mmrs={GameType.DEADLOCK: player.deadlock or 0},
        )
        if player.user.pk == GAME_MMR_APPROVE_USER.pk:
            _ensure_deadlock_rank(org_user)

    if force:
        _delete_events(
            org, GAME_MMR_DEADLOCK_EVENT_NAME, GAME_MMR_DEADLOCK_TOURNAMENT_NAME
        )
        Tournament.objects.nocache().filter(
            league=league, name=GAME_MMR_DOTA_TOURNAMENT_NAME
        ).delete()

    dota, _ = Tournament.objects.update_or_create(
        league=league,
        name=GAME_MMR_DOTA_TOURNAMENT_NAME,
        defaults={
            "steam_league_id": league.steam_league_id,
            "date_played": timezone.now() + timedelta(days=7),
            "state": "future",
            "tournament_type": "single_elimination",
            "game_type": GameType.DOTA2,
        },
    )
    dota.users.set(tournament_user_pks)

    event = (
        Event.objects.nocache()
        .filter(organization=org, name=GAME_MMR_DEADLOCK_EVENT_NAME)
        .select_related("tournament")
        .first()
    )
    if event is None or event.tournament is None:
        _delete_events(
            org, GAME_MMR_DEADLOCK_EVENT_NAME, GAME_MMR_DEADLOCK_TOURNAMENT_NAME
        )
        event = _deadlock_event(
            org,
            league,
            GAME_MMR_DEADLOCK_EVENT_NAME,
            GAME_MMR_DEADLOCK_TOURNAMENT_NAME,
            EventState.UPCOMING,
        )
    event.tournament.users.set(tournament_user_pks)
    print(f"    Created {GAME_MMR_ORG.name} with {len(GAME_MMR_PLAYERS)} users")


def reset_game_org_mmr_approve() -> dict[str, Any]:
    """Rebuild the Deadlock approve event with a pending signup for 8007."""
    with transaction.atomic():
        org = Organization.objects.nocache().get(pk=GAME_MMR_ORG.pk)
        league = League.objects.nocache().get(pk=GAME_MMR_LEAGUE.pk)
        _delete_events(
            org, GAME_MMR_APPROVE_EVENT_NAME, GAME_MMR_APPROVE_TOURNAMENT_NAME
        )
        org_user = OrgUser.objects.nocache().get(
            organization=org, user_id=GAME_MMR_APPROVE_USER.pk
        )
        set_org_mmr(
            org_user, GameType.DOTA2, GAME_MMR_APPROVE_DOTA, mark_verified=False
        )
        set_org_mmr(org_user, GameType.DEADLOCK, None, mark_verified=False)
        _ensure_deadlock_rank(org_user)
        event = _deadlock_event(
            org,
            league,
            GAME_MMR_APPROVE_EVENT_NAME,
            GAME_MMR_APPROVE_TOURNAMENT_NAME,
            EventState.SIGNUPS_OPEN,
        )
        signup = EventSignup.objects.create(
            event=event,
            user_id=GAME_MMR_APPROVE_USER.pk,
            status=SignupStatus.PENDING_APPROVAL,
        )
    for model in (Event, EventSignup, Tournament, PlayerDeadlockProfile):
        invalidate_model(model)
    invalidate_obj(org_user)
    return {
        "org_pk": org.pk,
        "event_pk": event.pk,
        "signup_pk": signup.pk,
        "user_pk": GAME_MMR_APPROVE_USER.pk,
        "dota_mmr": GAME_MMR_APPROVE_DOTA,
    }


def _user_payload(data: TestUser) -> dict[str, Any]:
    return {"pk": data.pk, "username": data.username}


def game_org_mmr_test_data() -> dict[str, Any]:
    """PKs and names the specs look up (never hardcoded there)."""
    org = Organization.objects.nocache().get(pk=GAME_MMR_ORG.pk)
    league = League.objects.nocache().get(pk=GAME_MMR_LEAGUE.pk)
    dota = Tournament.objects.nocache().get(
        league=league, name=GAME_MMR_DOTA_TOURNAMENT_NAME
    )
    event = Event.objects.nocache().get(
        organization=org, name=GAME_MMR_DEADLOCK_EVENT_NAME
    )
    deadlock = Tournament.objects.nocache().get(pk=event.tournament_id)
    return {
        "org": {"pk": org.pk, "name": org.name},
        "league": {"pk": league.pk, "name": league.name},
        "tournaments": {
            "dota": {"pk": dota.pk, "name": dota.name},
            "deadlock": {"pk": deadlock.pk, "name": deadlock.name},
        },
        "events": {"deadlock": {"pk": event.pk, "name": event.name}},
        "users": {
            "players": [
                _user_payload(p.user)
                for p in GAME_MMR_PLAYERS
                if p.user.username.startswith("gom_player_")
            ],
            "display": _user_payload(GAME_MMR_DISPLAY_USER),
            "edit": _user_payload(GAME_MMR_EDIT_USER),
            "approve": _user_payload(GAME_MMR_APPROVE_USER),
        },
    }
