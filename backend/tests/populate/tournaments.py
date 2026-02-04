"""
Tournament population functions for test database.
"""

import random
from datetime import date, timedelta

from django.db import transaction

from app.models import CustomUser, Game, PositionsModel, Team

from .constants import DTX_STEAM_LEAGUE_ID, TEST_STEAM_LEAGUE_ID, TOURNAMENT_USERS
from .utils import (
    REAL_TOURNAMENT_USERS,
    ensure_league_user,
    ensure_org_user,
    flush_redis_cache,
)


def populate_tournaments(force=False):
    """
    Creates 6 tournaments:
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

    # Tournament configurations
    # Names are descriptive of what feature each tournament tests
    # Player counts match team counts (teams x 5 players per team)
    # All use DTX league by default
    tournament_configs = [
        # All 6 bracket games completed - used for bracket badges, match stats tests
        {
            "name": "Completed Bracket Test",
            "users": 20,
            "teams": 4,
            "type": "double_elimination",
            "league": dtx_league,
        },
        # 2 games completed, 4 pending - used for partial bracket tests
        {
            "name": "Partial Bracket Test",
            "users": 20,
            "teams": 4,
            "type": "double_elimination",
            "league": dtx_league,
        },
        # 0 games completed, all pending - used for pending bracket tests
        {
            "name": "Pending Bracket Test",
            "users": 20,
            "teams": 4,
            "type": "double_elimination",
            "league": dtx_league,
        },
        # Used for captain draft and shuffle draft tests
        {
            "name": "Draft Test",
            "users": 30,
            "teams": 6,
            "type": "double_elimination",
            "league": dtx_league,
        },
        # Larger tournament for general testing
        {
            "name": "Large Tournament Test",
            "users": 40,
            "teams": 8,
            "type": "single_elimination",
            "league": dtx_league,
        },
        # Test League tournament - used for multi-org/league testing
        {
            "name": "Test League Tournament",
            "users": 20,
            "teams": 4,
            "type": "double_elimination",
            "league": test_league,
        },
    ]

    tournaments_created = 0

    for i, config in enumerate(tournament_configs):
        tournament_name = config["name"]
        user_count = config["users"]
        tournament_type = config["type"]
        league = config["league"]

        # Check if tournament with this name already exists
        if Tournament.objects.filter(name=tournament_name).exists() and not force:
            print(f"Tournament '{tournament_name}' already exists, skipping...")
            continue

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
            # Create tournament with league assignment
            tournament = Tournament.objects.create(
                name=tournament_name,
                date_played=tournament_date,
                state=state,
                tournament_type=tournament_type,
                league=league,
                steam_league_id=league.steam_league_id,
            )

            # Get random users for this tournament
            # Need users with Steam IDs for match generation
            users_with_steam = list(
                CustomUser.objects.filter(steamid__isnull=False).exclude(steamid=0)
            )
            all_users = list(CustomUser.objects.all())

            # Prioritize users with Steam IDs for team membership
            selected_users = random.sample(all_users, min(user_count, len(all_users)))

            # Add users to tournament
            tournament.users.set(selected_users)

            # Create OrgUser and LeagueUser records for tournament users
            org = league.organization
            if org:
                for user in selected_users:
                    org_user = ensure_org_user(user, org)
                    ensure_league_user(user, org_user, league)

            # Create teams based on config (5 players per team: 1 captain + 4 members)
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
            team_count = config.get("teams", 4)
            team_size = 5
            required_users = team_count * team_size

            # Get users with Steam IDs for team membership
            users_for_teams = users_with_steam[:required_users]

            if len(users_for_teams) >= required_users:
                for team_idx in range(team_count):
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
                    team.members.set(team_members)  # Captain included in members

            tournament.save()

            team_count = tournament.teams.count()
            print(
                f"Created tournament '{tournament_name}' with {len(selected_users)} users, "
                f"{team_count} teams (type: {tournament_type}, state: {state}, "
                f"league: {league.name})"
            )
            tournaments_created += 1

    print(
        f"Created {tournaments_created} new tournaments. Total tournaments in database: {Tournament.objects.count()}"
    )


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

    def create_or_get_user(username):
        """Create or get a user from TOURNAMENT_USERS data (Pydantic models)."""
        test_user = TOURNAMENT_USERS.get(username)
        if not test_user:
            raise ValueError(f"User '{username}' not found in TOURNAMENT_USERS")

        steam_id = test_user.steam_id
        mmr = test_user.mmr or 3000
        discord_id = test_user.discord_id
        pos_data = test_user.positions

        # Convert Steam ID 32-bit to 64-bit if provided
        steamid_64 = test_user.get_steam_id_64()

        # First, try to find existing user by discord_id
        user = CustomUser.objects.filter(discordId=discord_id).first()

        if not user and steamid_64:
            # Try to find by steamid (in case discord changed but steam is same)
            user = CustomUser.objects.filter(steamid=steamid_64).first()
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
                if steamid_64:
                    user.steamid = steamid_64
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
                steamid=steamid_64,
                mmr=mmr,
                positions=positions,
            )
            print(
                f"    Created user: {username} (mmr: {mmr}, steam: {steam_id or 'N/A'})"
            )
        else:
            # Update existing user data
            if user.steamid != steamid_64 and steamid_64:
                user.steamid = steamid_64
            if user.username != username:
                user.username = username
            if user.mmr != mmr:
                user.mmr = mmr
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
        # Create captain (data comes from TOURNAMENT_USERS Pydantic models)
        captain = create_or_get_user(team_config.captain_username)
        all_users.append(captain)

        # Create team members (captain is included in member_usernames)
        team_members = []
        for member_username in team_config.member_usernames:
            member = create_or_get_user(member_username)
            team_members.append(member)
            if member not in all_users:
                all_users.append(member)

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
