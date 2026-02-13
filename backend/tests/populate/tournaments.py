"""
Tournament population functions for test database.
"""

import random
from datetime import date, timedelta

from django.db import transaction

from app.models import CustomUser, Game, PositionsModel, Team
from tests.data.models import DynamicTournamentConfig, TestUser

from .constants import DTX_STEAM_LEAGUE_ID, TEST_STEAM_LEAGUE_ID, TOURNAMENT_USERS
from .utils import (
    REAL_TOURNAMENT_USERS,
    ensure_league_user,
    ensure_org_user,
    flush_redis_cache,
)


def create_dynamic_tournament(config: DynamicTournamentConfig, force: bool = False):
    """Create a tournament from a DynamicTournamentConfig.

    Args:
        config: The DynamicTournamentConfig with tournament settings
        force: If True, recreate tournament even if it exists

    Returns:
        Tournament: The created or existing Tournament instance
    """
    from app.models import League, Tournament

    # Check if tournament already exists
    existing = Tournament.objects.filter(name=config.name).first()
    if existing and not force:
        print(
            f"Tournament '{config.name}' already exists (pk={existing.pk}), skipping..."
        )
        return existing

    if existing and force:
        print(f"Deleting existing tournament '{config.name}' for recreation...")
        existing.delete()

    # Get the league by name
    league = League.objects.filter(name=config.league_name).first()
    if not league:
        print(
            f"League '{config.league_name}' not found. Run populate_organizations_and_leagues first."
        )
        return None

    # Get users with Steam IDs for team membership
    users_with_steam = list(
        CustomUser.objects.filter(steamid__isnull=False).exclude(steamid=0)
    )
    all_users = list(CustomUser.objects.all())

    if len(all_users) < config.user_count:
        print(
            f"Not enough users ({len(all_users)}) for tournament '{config.name}' (needs {config.user_count})"
        )
        return None

    # Generate random date (within last 3 months to next 3 months)
    base_date = date.today()
    random_days = random.randint(-90, 90)
    tournament_date = base_date + timedelta(days=random_days)

    # Set state based on date
    if tournament_date < base_date:
        state = "past"
    elif tournament_date > base_date:
        state = "future"
    else:
        state = "in_progress"

    with transaction.atomic():
        # Create tournament with specific pk if provided
        tournament = Tournament.objects.create(
            pk=config.pk,
            name=config.name,
            date_played=tournament_date,
            state=state,
            tournament_type=config.tournament_type,
            league=league,
            steam_league_id=league.steam_league_id,
        )

        # Select random users for this tournament
        selected_users = random.sample(
            all_users, min(config.user_count, len(all_users))
        )
        tournament.users.set(selected_users)

        # Create OrgUser and LeagueUser records
        org = league.organization
        if org:
            for user in selected_users:
                org_user = ensure_org_user(user, org)
                ensure_league_user(user, org_user, league)

        # Create teams (5 players per team)
        team_name_pool = [
            "Team Alpha",
            "Team Beta",
            "Team Gamma",
            "Team Delta",
            "Team Epsilon",
            "Team Zeta",
            "Team Eta",
            "Team Theta",
        ]
        team_size = 5
        required_users = config.team_count * team_size
        users_for_teams = users_with_steam[:required_users]

        if len(users_for_teams) >= required_users:
            for team_idx in range(config.team_count):
                team_name = (
                    team_name_pool[team_idx]
                    if team_idx < len(team_name_pool)
                    else f"Team {team_idx + 1}"
                )
                team_members = users_for_teams[
                    team_idx * team_size : (team_idx + 1) * team_size
                ]
                captain = team_members[0] if team_members else None

                team = Team.objects.create(
                    tournament=tournament,
                    name=team_name,
                    captain=captain,
                    draft_order=team_idx + 1,
                )
                team.members.set(team_members)

        tournament.save()

        print(
            f"Created tournament '{config.name}' (pk={tournament.pk}) with {len(selected_users)} users, "
            f"{tournament.teams.count()} teams (type: {config.tournament_type}, league: {league.name})"
        )

        return tournament


def create_dyn_tournaments(force: bool = False):
    """Create all dynamic tournaments from data/tournaments.py.

    Imports all objects from tests.data.tournaments and creates any
    that are DynamicTournamentConfig instances.

    Args:
        force: If True, recreate tournaments even if they exist

    Returns:
        list[Tournament]: List of created Tournament instances
    """
    from tests.data import tournaments as tournament_data

    created = []
    for name in dir(tournament_data):
        obj = getattr(tournament_data, name)
        if isinstance(obj, DynamicTournamentConfig):
            tournament = create_dynamic_tournament(obj, force=force)
            if tournament:
                created.append(tournament)

    print(f"Created {len(created)} dynamic tournaments")
    return created


def populate_tournaments(force=False):
    """
    Creates 6 tournaments from DynamicTournamentConfig objects:
    - 5 tournaments assigned to DTX League (steam_league_id=17929)
    - 1 tournament assigned to Test League (steam_league_id=17930)

    Args:
        force (bool): If True, create tournaments even if some already exist.
    """
    from app.models import League, Tournament

    # Check if tournaments already exist
    existing_tournaments = Tournament.objects.count()
    if existing_tournaments >= 6 and not force:
        print(
            f"Database already has {existing_tournaments} tournaments (>=6). Use force=True to create anyway."
        )
        return

    # Ensure we have enough users
    total_users = CustomUser.objects.count()
    if total_users < 40:
        print(
            f"Not enough users in database ({total_users}). Need at least 40 users to create tournaments."
        )
        print("Run populate_users first to create users.")
        return

    # Get the DTX and Test leagues
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    test_league = League.objects.filter(steam_league_id=TEST_STEAM_LEAGUE_ID).first()

    if not dtx_league or not test_league:
        print("Leagues not found. Run populate_organizations_and_leagues first.")
        return

    # Create all dynamic tournaments from Pydantic configs
    tournaments = create_dyn_tournaments(force=force)

    print(f"Total tournaments in database: {Tournament.objects.count()}")


def populate_real_tournament_38(force=False):
    """
    Creates test data based on real production Tournament 38.

    Uses Pydantic models from tests/data for consistent, type-safe data:
    - Tournament config: REAL_TOURNAMENT_38 from tests/data/tournaments.py
    - Team configs: REAL_TOURNAMENT_38_TEAMS from tests/data/teams.py
    - User data: TOURNAMENT_USERS from tests/data/users.py

    Tournament 38 details:
    - Name: "Real Tournament 38" (the date it was played)
    - Type: double_elimination
    - 4 teams with 5 players each (20 total)
    - Real Steam IDs for most players (enables league sync testing)
    - Assigned to DTX League (steam_league_id=17929)

    This data can be used to test:
    - Steam league match auto-syncing (players have real Steam IDs)
    - Bracket game linking with real match data
    - 4-team double elimination bracket structure

    Match IDs: Steam matches should auto-sync from DTX League (17929)

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from datetime import datetime

    from django.utils import timezone

    from app.models import League, Tournament
    from tests.data.teams import REAL_TOURNAMENT_38_TEAMS
    from tests.data.tournaments import REAL_TOURNAMENT_38

    # Use Pydantic model for tournament config (single source of truth)
    tournament_config = REAL_TOURNAMENT_38
    team_configs = REAL_TOURNAMENT_38_TEAMS

    # Get the DTX league
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    if not dtx_league:
        print("DTX League not found. Run populate_organizations_and_leagues first.")
        return None

    # Check if tournament already exists
    existing_tournament = Tournament.objects.filter(name=tournament_config.name).first()

    if existing_tournament and not force:
        print(
            f"Tournament '{tournament_config.name}' already exists. Use force=True to recreate."
        )
        return existing_tournament

    if force and existing_tournament:
        print(f"Deleting existing tournament '{tournament_config.name}'...")
        existing_tournament.delete()

    print(f"Creating '{tournament_config.name}' with real production data...")

    def create_or_get_user(test_user: TestUser):
        """Create or get a user from a TestUser Pydantic model."""
        username = test_user.username
        steam_id = test_user.steam_id
        mmr = test_user.mmr or 3000
        discord_id = test_user.discord_id
        pos_data = test_user.positions

        # Get 32-bit Friend ID (Dotabuff)
        steam_account_id = test_user.get_steam_account_id()

        # First, try to find existing user by discord_id
        user = CustomUser.objects.filter(discordId=discord_id).first()

        if not user and steam_account_id:
            # Try to find by steam_account_id (in case discord changed but steam is same)
            user = CustomUser.objects.filter(steam_account_id=steam_account_id).first()
            if user:
                # Update discord_id to match production
                user.discordId = discord_id
                user.save()
                print(f"    Updated user discord_id: {username}")

        if not user:
            # Try to find by username (mock users might have same username)
            user = CustomUser.objects.filter(username=username).first()
            if user:
                # Update to match production data
                user.discordId = discord_id
                if steam_account_id:
                    user.steam_account_id = steam_account_id
                user.save()
                print(f"    Updated user from username match: {username}")

        if not user:
            # Create new user with real position data
            positions = PositionsModel.objects.create(
                carry=pos_data.carry if pos_data else 3,
                mid=pos_data.mid if pos_data else 3,
                offlane=pos_data.offlane if pos_data else 3,
                soft_support=pos_data.soft_support if pos_data else 3,
                hard_support=pos_data.hard_support if pos_data else 3,
            )
            user = CustomUser.objects.create(
                discordId=discord_id,
                username=username,
                steam_account_id=steam_account_id,
                positions=positions,
            )
            print(
                f"    Created user: {username} (mmr: {mmr}, steam: {steam_id or 'N/A'})"
            )
        else:
            # Update existing user data
            if user.steam_account_id != steam_account_id and steam_account_id:
                user.steam_account_id = steam_account_id
            if user.username != username:
                user.username = username
            # Update positions if we have real data
            if pos_data and user.positions:
                user.positions.carry = pos_data.carry
                user.positions.mid = pos_data.mid
                user.positions.offlane = pos_data.offlane
                user.positions.soft_support = pos_data.soft_support
                user.positions.hard_support = pos_data.hard_support
                user.positions.save()
            user.save()

        return user

    # Parse date from config
    if tournament_config.date_played:
        date_played = timezone.make_aware(
            datetime.strptime(tournament_config.date_played, "%Y-%m-%d")
        )
    else:
        date_played = timezone.now()

    # Create tournament using Pydantic config
    tournament = Tournament.objects.create(
        name=tournament_config.name,
        date_played=date_played,
        state=tournament_config.state,
        tournament_type=tournament_config.tournament_type,
        league=dtx_league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )

    all_users = []
    teams = []

    print("  Creating users and teams...")
    # Use team configs from Pydantic models (already in draft order)
    for team_config in team_configs:
        # Create captain (data comes from TestUser Pydantic models)
        captain = create_or_get_user(team_config.captain)
        all_users.append(captain)

        # Create team members (captain is included in members)
        team_members = []
        for member in team_config.members:
            db_member = create_or_get_user(member)
            team_members.append(db_member)
            if db_member not in all_users:
                all_users.append(db_member)

        # Create team with captain
        team = Team.objects.create(
            tournament=tournament,
            name=team_config.name,
            captain=captain,
            draft_order=team_config.draft_order,
        )
        team.members.set(team_members)  # Captain included in members
        teams.append(team)
        print(f"    Created team: {team_config.name} (captain: {captain.username})")

    # Add all users to tournament
    tournament.users.set(all_users)

    # Create OrgUser and LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for user in all_users:
            org_user = ensure_org_user(user, org)
            ensure_league_user(user, org_user, dtx_league)

    # Create bracket games (6 games for 4-team double elimination)
    # Based on actual bracket state from /api/bracket/tournaments/38/
    #
    # API Data (as of tournament completion):
    # | Game | Round | Bracket | Status    | Radiant              | Dire                 | Winner        |
    # |------|-------|---------|-----------|----------------------|----------------------|---------------|
    # | 22   | 1     | Winners | Completed | gglive (299)         | vrm.mtl (302)        | vrm.mtl       |
    # | 23   | 1     | Winners | Completed | benevolentgremlin    | ethan0688_ (301)     | ethan0688_    |
    # | 20   | 1     | Losers  | Completed | gglive (299)         | benevolentgremlin    | gglive        |
    # | 24   | 2     | Winners | Pending   | vrm.mtl (302)        | ethan0688_ (301)     | -             |
    # | 21   | 2     | Losers  | Pending   | gglive (299)         | (WF loser)           | -             |
    # | 19   | 1     | GF      | Pending   | (WF winner)          | (LF winner)          | -             |
    #
    # teams[0] = gglive's Team, teams[1] = benevolentgremlin's Team
    # teams[2] = ethan0688_'s Team, teams[3] = vrm.mtl's Team

    bracket_structure = [
        # Winners Round 1 - COMPLETED
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 0,
            "radiant": teams[0],
            "dire": teams[3],
            "winner": teams[3],
            "status": "completed",
        },  # gglive vs vrm.mtl -> vrm.mtl wins
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 1,
            "radiant": teams[1],
            "dire": teams[2],
            "winner": teams[2],
            "status": "completed",
        },  # benevolentgremlin vs ethan0688_ -> ethan0688_ wins
        # Losers Round 1 - COMPLETED (losers from WR1)
        {
            "round": 1,
            "bracket_type": "losers",
            "position": 0,
            "radiant": teams[0],
            "dire": teams[1],
            "winner": teams[0],
            "status": "completed",
        },  # gglive vs benevolentgremlin -> gglive wins
        # Winners Final - PENDING (winners from WR1)
        {
            "round": 2,
            "bracket_type": "winners",
            "position": 0,
            "radiant": teams[3],
            "dire": teams[2],
            "winner": None,
            "status": "pending",
        },  # vrm.mtl vs ethan0688_
        # Losers Final - PENDING (LR1 winner vs WF loser)
        {
            "round": 2,
            "bracket_type": "losers",
            "position": 0,
            "radiant": teams[0],
            "dire": None,
            "winner": None,
            "status": "pending",
        },  # gglive vs (WF loser TBD)
        # Grand Final - PENDING
        {
            "round": 1,
            "bracket_type": "grand_finals",
            "position": 0,
            "radiant": None,
            "dire": None,
            "winner": None,
            "status": "pending",
        },  # (WF winner) vs (LF winner)
    ]

    print("  Creating bracket games...")
    games = []
    for idx, bracket_info in enumerate(bracket_structure):
        game = Game.objects.create(
            tournament=tournament,
            round=bracket_info["round"],
            bracket_type=bracket_info["bracket_type"],
            position=bracket_info["position"],
            elimination_type="double",
            radiant_team=bracket_info.get("radiant"),
            dire_team=bracket_info.get("dire"),
            winning_team=bracket_info.get("winner"),
            status=bracket_info.get("status", "pending"),
        )
        games.append(game)

    # Set up bracket links (winner/loser advancement)
    if len(games) >= 6:
        # Winners R1 M1 -> Winners Final (radiant) + Losers R1 (radiant)
        games[0].next_game = games[3]
        games[0].next_game_slot = "radiant"
        games[0].loser_next_game = games[2]
        games[0].loser_next_game_slot = "radiant"
        games[0].save()

        # Winners R1 M2 -> Winners Final (dire) + Losers R1 (dire)
        games[1].next_game = games[3]
        games[1].next_game_slot = "dire"
        games[1].loser_next_game = games[2]
        games[1].loser_next_game_slot = "dire"
        games[1].save()

        # Losers R1 -> Losers Final (radiant)
        games[2].next_game = games[4]
        games[2].next_game_slot = "radiant"
        games[2].save()

        # Winners Final -> Grand Final (radiant) + Losers Final (dire)
        games[3].next_game = games[5]
        games[3].next_game_slot = "radiant"
        games[3].loser_next_game = games[4]
        games[3].loser_next_game_slot = "dire"
        games[3].save()

        # Losers Final -> Grand Final (dire)
        games[4].next_game = games[5]
        games[4].next_game_slot = "dire"
        games[4].save()

    print(
        f"Created tournament '{tournament_config.name}' with {len(teams)} teams, "
        f"{len(all_users)} users, and {len(games)} bracket games"
    )
    print(
        f"Note: Steam matches should auto-sync from DTX League (steam_league_id={DTX_STEAM_LEAGUE_ID})"
    )

    # Flush Redis cache
    flush_redis_cache()

    return tournament
