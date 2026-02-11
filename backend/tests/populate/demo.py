"""
Demo tournament population functions for video recording.
"""

import random

from .constants import DTX_STEAM_LEAGUE_ID, TOURNAMENT_USERS
from .utils import (
    REAL_TOURNAMENT_USERS,
    ensure_league_user,
    ensure_org_user,
    fetch_discord_avatars_for_users,
    flush_redis_cache,
    get_or_create_demo_user,
)


def populate_demo_herodraft_tournament(force=False):
    """
    Create Demo HeroDraft Tournament for video recording.

    Creates a tournament with 2 teams (5 players each) for hero draft demos.
    Uses Real Tournament 38 users with Discord avatars.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from django.utils import timezone

    from app.models import DraftTeam, Game, HeroDraft, League, Team, Tournament
    from tests.data.tournaments import DEMO_HERODRAFT_TOURNAMENT

    # Use Pydantic config for tournament (single source of truth)
    tournament_config = DEMO_HERODRAFT_TOURNAMENT

    # Get the DTX league
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()

    existing = Tournament.objects.filter(name=tournament_config.name).first()
    if existing and not force:
        print(
            f"Tournament '{tournament_config.name}' already exists. Use force=True to recreate."
        )
        return existing

    if force and existing:
        print(f"Deleting existing tournament '{tournament_config.name}'...")
        existing.delete()

    print(f"Creating '{tournament_config.name}' for hero draft demos...")

    # Use TestUser objects for type-safe usernames
    vrm_mtl = TOURNAMENT_USERS["vrm.mtl"]
    tornope = TOURNAMENT_USERS["tornope"]
    nimstria1 = TOURNAMENT_USERS["nimstria1"]
    thekingauto = TOURNAMENT_USERS["thekingauto"]
    clarexlauda = TOURNAMENT_USERS["clarexlauda"]
    ethan0688_ = TOURNAMENT_USERS["ethan0688_"]
    just__khang = TOURNAMENT_USERS["just__khang"]
    heffdawgz = TOURNAMENT_USERS["heffdawgz"]
    pushingshots = TOURNAMENT_USERS["pushingshots"]
    anil98765 = TOURNAMENT_USERS["anil98765"]

    # Team A and B usernames using TestUser objects
    team_a_usernames = [
        vrm_mtl.username,
        tornope.username,
        nimstria1.username,
        thekingauto.username,
        clarexlauda.username,
    ]
    team_b_usernames = [
        ethan0688_.username,
        just__khang.username,
        heffdawgz.username,
        pushingshots.username,
        anil98765.username,
    ]

    team_a_users = [
        get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in team_a_usernames
    ]
    team_b_users = [
        get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in team_b_usernames
    ]
    all_users = team_a_users + team_b_users

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    fetch_discord_avatars_for_users(all_users)

    tournament = Tournament.objects.create(
        name=tournament_config.name,
        date_played=timezone.now(),
        state="in_progress",
        tournament_type=tournament_config.tournament_type,
        league=dtx_league,
    )
    tournament.users.set(all_users)

    # Create LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for user in all_users:
            org_user = ensure_org_user(user, org, mmr=random.randint(2000, 8000))
            ensure_league_user(user, org_user, dtx_league)

    # Create teams using config from tests/data
    team_a = Team.objects.create(
        tournament=tournament,
        name="Demo Team Alpha",
        captain=team_a_users[0],  # vrm.mtl
        draft_order=1,
    )
    team_a.members.set(team_a_users)

    team_b = Team.objects.create(
        tournament=tournament,
        name="Demo Team Beta",
        captain=team_b_users[0],  # ethan0688_
        draft_order=2,
    )
    team_b.members.set(team_b_users)

    # Create a single bracket game for hero draft
    game = Game.objects.create(
        tournament=tournament,
        round=1,
        bracket_type="winners",
        position=0,
        elimination_type="double",
        radiant_team=team_a,
        dire_team=team_b,
        status="pending",
    )

    # Create HeroDraft for this game
    # State is "completed" so it doesn't trigger the active_drafts banner
    # for captains in E2E tests. Demo reset sets it back to
    # "waiting_for_captains" before recording.
    herodraft = HeroDraft.objects.create(
        game=game,
        state="completed",
    )

    # Create draft teams
    DraftTeam.objects.create(
        draft=herodraft,
        tournament_team=team_a,
        reserve_time_remaining=90000,
    )
    DraftTeam.objects.create(
        draft=herodraft,
        tournament_team=team_b,
        reserve_time_remaining=90000,
    )

    print(f"Created '{tournament_config.name}' with 2 teams, HeroDraft ready")
    flush_redis_cache()

    return tournament


def populate_demo_captaindraft_tournament(force=False):
    """
    Create Demo Captain Draft Tournament for video recording.

    Creates a tournament with 16 players (no teams yet) for captain draft demos.
    Uses Real Tournament 38 users with Discord avatars.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from django.utils import timezone

    from app.models import Draft, League, Tournament

    TOURNAMENT_NAME = "Demo Captain Draft Tournament"

    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()

    existing = Tournament.objects.filter(name=TOURNAMENT_NAME).first()
    if existing and not force:
        print(
            f"Tournament '{TOURNAMENT_NAME}' already exists. Use force=True to recreate."
        )
        return existing

    if force and existing:
        print(f"Deleting existing tournament '{TOURNAMENT_NAME}'...")
        existing.delete()

    print(f"Creating '{TOURNAMENT_NAME}' for captain draft demos...")

    # Use first 16 Real Tournament users
    usernames = list(REAL_TOURNAMENT_USERS.keys())[:16]
    users = [get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="future",  # Before draft
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

    # Create LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for user in users:
            org_user = ensure_org_user(user, org, mmr=random.randint(2000, 8000))
            ensure_league_user(user, org_user, dtx_league)

    # Create draft for this tournament (shuffle mode for demo)
    Draft.objects.create(
        tournament=tournament,
        draft_style="shuffle",
    )

    print(f"Created '{TOURNAMENT_NAME}' with 16 players, Draft ready")
    flush_redis_cache()

    return tournament


def populate_demo_snake_draft_tournament(force=False):
    """
    Create Demo Snake Draft Tournament for video recording.

    Creates a tournament with 16 players and 4 teams for snake draft demos.
    Uses Real Tournament 38 users with Discord avatars.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from django.utils import timezone

    from app.models import Draft, League, Team, Tournament

    TOURNAMENT_NAME = "Demo Snake Draft Tournament"

    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()

    existing = Tournament.objects.filter(name=TOURNAMENT_NAME).first()
    if existing and not force:
        print(
            f"Tournament '{TOURNAMENT_NAME}' already exists. Use force=True to recreate."
        )
        return existing

    if force and existing:
        print(f"Deleting existing tournament '{TOURNAMENT_NAME}'...")
        existing.delete()

    print(f"Creating '{TOURNAMENT_NAME}' for snake draft demos...")

    # Use first 20 Real Tournament users (4 captains + 16 players)
    usernames = list(REAL_TOURNAMENT_USERS.keys())[:20]
    users = [get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="in_progress",  # Ready for drafting
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

    # Create LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for user in users:
            org_user = ensure_org_user(user, org, mmr=random.randint(2000, 8000))
            ensure_league_user(user, org_user, dtx_league)

    # Create 4 teams with captains (first 4 users)
    team_names = ["Team Alpha", "Team Beta", "Team Gamma", "Team Delta"]
    for i, team_name in enumerate(team_names):
        captain = users[i]
        team = Team.objects.create(
            tournament=tournament,
            name=team_name,
            captain=captain,
            draft_order=i + 1,
        )
        team.members.add(captain)

    # Create draft for this tournament (snake mode)
    draft = Draft.objects.create(
        tournament=tournament,
        draft_style="snake",
    )

    # Initialize draft rounds
    draft.build_rounds()
    draft.rebuild_teams()
    draft.save()

    print(f"Created '{TOURNAMENT_NAME}' with 4 teams, 20 players, Snake Draft ready")
    flush_redis_cache()

    return tournament


def populate_demo_shuffle_draft_tournament(force=False):
    """
    Create Demo Shuffle Draft Tournament for video recording.

    Creates a tournament with 16 players and 4 teams for shuffle draft demos.
    Uses Real Tournament 38 users with Discord avatars.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from django.utils import timezone

    from app.models import Draft, League, Team, Tournament

    TOURNAMENT_NAME = "Demo Shuffle Draft Tournament"

    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()

    existing = Tournament.objects.filter(name=TOURNAMENT_NAME).first()
    if existing and not force:
        print(
            f"Tournament '{TOURNAMENT_NAME}' already exists. Use force=True to recreate."
        )
        return existing

    if force and existing:
        print(f"Deleting existing tournament '{TOURNAMENT_NAME}'...")
        existing.delete()

    print(f"Creating '{TOURNAMENT_NAME}' for shuffle draft demos...")

    # Use first 20 Real Tournament users (4 captains + 16 players)
    usernames = list(REAL_TOURNAMENT_USERS.keys())[:20]
    users = [get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="in_progress",  # Ready for drafting
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

    # Create LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for user in users:
            org_user = ensure_org_user(user, org, mmr=random.randint(2000, 8000))
            ensure_league_user(user, org_user, dtx_league)

    # Create 4 teams with captains (first 4 users)
    team_names = ["Team Alpha", "Team Beta", "Team Gamma", "Team Delta"]
    for i, team_name in enumerate(team_names):
        captain = users[i]
        team = Team.objects.create(
            tournament=tournament,
            name=team_name,
            captain=captain,
            draft_order=i + 1,
        )
        team.members.add(captain)

    # Create draft for this tournament (shuffle mode)
    draft = Draft.objects.create(
        tournament=tournament,
        draft_style="shuffle",
    )

    # Initialize draft rounds
    draft.build_rounds()
    draft.rebuild_teams()
    draft.save()

    print(f"Created '{TOURNAMENT_NAME}' with 4 teams, 20 players, Shuffle Draft ready")
    flush_redis_cache()

    return tournament


def populate_demo_csv_org(force=False):
    """Create Demo CSV Organization and League for demo video recording.

    Separate from CSV Import Org (used by E2E tests) to avoid clobbering test data.
    Admin user is added as org admin so the demo can create tournaments.
    """
    from app.models import CustomUser, League, Organization
    from tests.data.leagues import DEMO_CSV_LEAGUE
    from tests.data.organizations import DEMO_CSV_ORG
    from tests.data.users import ADMIN_USER

    demo_org, created = Organization.objects.update_or_create(
        name=DEMO_CSV_ORG.name,
        defaults={
            "description": DEMO_CSV_ORG.description,
            "logo": "",
            "rules_template": DEMO_CSV_ORG.rules_template,
            "timezone": DEMO_CSV_ORG.timezone,
        },
    )
    print(f"  {'Created' if created else 'Updated'} organization: {DEMO_CSV_ORG.name}")

    demo_league, created = League.objects.update_or_create(
        steam_league_id=DEMO_CSV_LEAGUE.steam_league_id,
        defaults={
            "name": DEMO_CSV_LEAGUE.name,
            "description": DEMO_CSV_LEAGUE.description,
            "rules": DEMO_CSV_LEAGUE.rules,
            "prize_pool": "",
            "timezone": DEMO_CSV_LEAGUE.timezone,
        },
    )
    if demo_league.organization != demo_org:
        demo_league.organization = demo_org
        demo_league.save()
    print(f"  {'Created' if created else 'Updated'} league: {DEMO_CSV_LEAGUE.name}")

    if demo_org.default_league != demo_league:
        demo_org.default_league = demo_league
        demo_org.save()

    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user and admin_user not in demo_org.admins.all():
        demo_org.admins.add(admin_user)
        print(f"  Added {admin_user.username} as admin of {DEMO_CSV_ORG.name}")

    print(f"  Demo CSV ready: org={demo_org.pk}, league={demo_league.pk}")
    return demo_org, demo_league


def populate_demo_tournaments(force=False):
    """Create all demo tournaments for video recording."""
    populate_demo_herodraft_tournament(force)
    populate_demo_captaindraft_tournament(force)
    populate_demo_snake_draft_tournament(force)
    populate_demo_shuffle_draft_tournament(force)
    populate_demo_csv_org(force)
