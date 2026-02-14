"""
Bracket scenario population for test database.

Contains functions for creating bracket-related test scenarios:
- populate_bracket_linking_scenario: Creates data for bracket match linking tests
- populate_bracket_unset_winner_tournament: Creates data for unset winner E2E tests
"""

import random
from datetime import date

from app.models import CustomUser

from .constants import DTX_STEAM_LEAGUE_ID
from .utils import _ensure_league_user, _ensure_org_user, _flush_redis_cache


def populate_bracket_linking_scenario(force=False):
    """
    Creates test data for the bracket match linking feature.

    Creates a tournament "Bracket Linking Test" with:
    - Assigned to DTX League (steam_league_id=17929)
    - 4 teams with 5 players each (20 users with steam IDs)
    - Bracket games (winners round 1, losers bracket, grand finals)
    - 6 Steam matches in DTX League with different player overlap tiers:
      - 2 matches with all 10 players (tier: all_players)
      - 2 matches with both captains + some players (tier: captains_plus)
      - 2 matches with both captains only (tier: captains_only)

    Match IDs: 9100000001-9100000010 (avoids conflict with other populate functions)

    Requires: populate_organizations_and_leagues must be run first.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from datetime import datetime

    from app.models import CustomUser, Game, League, PositionsModel, Team, Tournament
    from steam.models import Match, PlayerMatchStats

    TOURNAMENT_NAME = "Bracket Linking Test"
    OLD_TOURNAMENT_NAME = "Link Test Tournament"  # Handle renamed tournament
    BASE_MATCH_ID = 9100000001

    # Get the DTX league (should be created by populate_organizations_and_leagues)
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    if not dtx_league:
        print(f"DTX League not found. Run populate_organizations_and_leagues first.")
        return None

    # Check if tournament already exists (check both old and new names)
    existing_tournament = Tournament.objects.filter(name=TOURNAMENT_NAME).first()
    old_tournament = Tournament.objects.filter(name=OLD_TOURNAMENT_NAME).first()

    if existing_tournament and not force:
        print(
            f"Tournament '{TOURNAMENT_NAME}' already exists. Use force=True to recreate."
        )
        return existing_tournament

    # Delete existing data if force=True
    if force:
        # Always clean up matches in our ID range
        deleted_matches = Match.objects.filter(
            match_id__gte=BASE_MATCH_ID, match_id__lt=BASE_MATCH_ID + 10
        ).delete()
        if deleted_matches[0] > 0:
            print(f"  Deleted {deleted_matches[0]} existing matches in ID range")

        # Delete old tournament (renamed)
        if old_tournament:
            print(f"Deleting old tournament '{OLD_TOURNAMENT_NAME}'...")
            old_tournament.delete()

        # Delete current tournament
        if existing_tournament:
            print(f"Deleting existing tournament '{TOURNAMENT_NAME}'...")
            existing_tournament.delete()

    print(f"Creating '{TOURNAMENT_NAME}' with bracket linking test data...")

    # Create 20 users with unique steam IDs for the 4 teams
    team_users = []
    for i in range(20):
        discord_id = str(200000000000000000 + i)
        username = f"link_test_player_{i}"
        steam_account_id = 34272 + i  # Unique 32-bit Friend IDs for linking

        user, created = CustomUser.objects.get_or_create(
            discordId=discord_id,
            defaults={
                "username": username,
                "steam_account_id": steam_account_id,
            },
        )
        if created:
            # Create positions for new user
            positions = PositionsModel.objects.create(
                carry=3, mid=3, offlane=3, soft_support=3, hard_support=3
            )
            user.positions = positions
            user.save()
        elif user.steam_account_id != steam_account_id:
            # Ensure Friend ID is set correctly
            user.steam_account_id = steam_account_id
            user.save()

        # Ensure steamid is computed (may be NULL if user existed before save() override)
        if user.steamid is None and user.steam_account_id is not None:
            user.save()

        team_users.append(user)

    # Create tournament with DTX league
    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=dtx_league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )

    # Add all users to tournament
    tournament.users.set(team_users)

    # Create OrgUser and LeagueUser records for tournament users
    org = dtx_league.organization
    if org:
        for i, user in enumerate(team_users):
            org_user = _ensure_org_user(user, org, mmr=3000 + (i * 100))
            _ensure_league_user(user, org_user, dtx_league)

    # Create 4 teams with 5 players each
    team_names = ["Link Alpha", "Link Beta", "Link Gamma", "Link Delta"]
    teams = []
    for team_idx, team_name in enumerate(team_names):
        team_members = team_users[team_idx * 5 : (team_idx + 1) * 5]
        captain = team_members[0]

        team = Team.objects.create(
            tournament=tournament,
            name=team_name,
            captain=captain,
            draft_order=team_idx + 1,
        )
        team.members.set(team_members)  # Captain included in members
        teams.append(team)

    print(f"  Created 4 teams: {', '.join(team_names)}")

    # Create bracket games (6 games for 4-team double elimination)
    bracket_structure = [
        {"round": 1, "bracket_type": "winners", "position": 0},  # WR1 M1
        {"round": 1, "bracket_type": "winners", "position": 1},  # WR1 M2
        {"round": 1, "bracket_type": "losers", "position": 0},  # LR1
        {"round": 2, "bracket_type": "winners", "position": 0},  # Winners Final
        {"round": 2, "bracket_type": "losers", "position": 0},  # Losers Final
        {"round": 1, "bracket_type": "grand_finals", "position": 0},  # Grand Final
    ]

    games = []
    for idx, bracket_info in enumerate(bracket_structure):
        # Assign teams to first round games only
        if idx == 0:
            radiant_team, dire_team = teams[0], teams[1]
        elif idx == 1:
            radiant_team, dire_team = teams[2], teams[3]
        else:
            radiant_team, dire_team = None, None  # Later rounds TBD

        game = Game.objects.create(
            tournament=tournament,
            round=bracket_info["round"],
            bracket_type=bracket_info["bracket_type"],
            position=bracket_info["position"],
            elimination_type="double",
            radiant_team=radiant_team,
            dire_team=dire_team,
            status="pending",
        )
        games.append(game)

    # Set up bracket links
    if len(games) >= 6:
        games[0].next_game = games[3]
        games[0].next_game_slot = "radiant"
        games[0].loser_next_game = games[2]
        games[0].loser_next_game_slot = "radiant"
        games[0].save()

        games[1].next_game = games[3]
        games[1].next_game_slot = "dire"
        games[1].loser_next_game = games[2]
        games[1].loser_next_game_slot = "dire"
        games[1].save()

        games[2].next_game = games[4]
        games[2].next_game_slot = "radiant"
        games[2].save()

        games[3].next_game = games[5]
        games[3].next_game_slot = "radiant"
        games[3].loser_next_game = games[4]
        games[3].loser_next_game_slot = "dire"
        games[3].save()

        games[4].next_game = games[5]
        games[4].next_game_slot = "dire"
        games[4].save()

    print(f"  Created {len(games)} bracket games")

    # Now create 6 unlinked Steam matches in the league with different tiers
    # Use teams[0] vs teams[1] as the test matchup
    radiant_team = teams[0]
    dire_team = teams[1]
    radiant_members = list(radiant_team.members.all())
    dire_members = list(dire_team.members.all())
    radiant_captain = radiant_team.captain
    dire_captain = dire_team.captain

    # Create matches on the tournament day (today)
    # Start at 10 AM tournament day
    from datetime import time as dt_time
    from datetime import timezone as dt_tz

    tournament_start = datetime.combine(date.today(), dt_time(10, 0), tzinfo=dt_tz.utc)
    base_time = int(tournament_start.timestamp())
    match_interval = 3600  # 1 hour between matches

    match_configs = [
        # Tier: all_players - all 10 players present
        {
            "tier": "all_players",
            "radiant_players": radiant_members,
            "dire_players": dire_members,
        },
        {
            "tier": "all_players",
            "radiant_players": radiant_members,
            "dire_players": dire_members,
        },
        # Tier: captains_plus - both captains + 2 other players per team
        {
            "tier": "captains_plus",
            "radiant_players": [radiant_captain] + radiant_members[1:3],
            "dire_players": [dire_captain] + dire_members[1:3],
        },
        {
            "tier": "captains_plus",
            "radiant_players": [radiant_captain] + radiant_members[2:4],
            "dire_players": [dire_captain] + dire_members[2:4],
        },
        # Tier: captains_only - only both captains
        {
            "tier": "captains_only",
            "radiant_players": [radiant_captain],
            "dire_players": [dire_captain],
        },
        {
            "tier": "captains_only",
            "radiant_players": [radiant_captain],
            "dire_players": [dire_captain],
        },
    ]

    matches_created = 0
    for idx, config in enumerate(match_configs):
        match_id = BASE_MATCH_ID + idx
        start_time = base_time + (idx * match_interval)

        # Create match
        match = Match.objects.create(
            match_id=match_id,
            radiant_win=idx % 2 == 0,  # Alternate wins
            duration=random.randint(1500, 3300),
            start_time=start_time,
            game_mode=2,  # Captain's Mode
            lobby_type=1,
            league_id=DTX_STEAM_LEAGUE_ID,
        )

        # Create player stats for each player in the match
        radiant_players = config["radiant_players"]
        dire_players = config["dire_players"]

        for slot_idx, player in enumerate(radiant_players):
            steam_id_64 = player.steamid or (
                player.steam_account_id + CustomUser.STEAM_ID_64_BASE
                if player.steam_account_id
                else None
            )
            PlayerMatchStats.objects.update_or_create(
                match=match,
                steam_id=steam_id_64,
                defaults={
                    "user": player,
                    "player_slot": slot_idx,
                    "hero_id": random.randint(1, 130),
                    "kills": random.randint(2, 15),
                    "deaths": random.randint(1, 10),
                    "assists": random.randint(5, 25),
                    "gold_per_min": random.randint(300, 600),
                    "xp_per_min": random.randint(400, 700),
                    "last_hits": random.randint(50, 300),
                    "denies": random.randint(0, 20),
                    "hero_damage": random.randint(10000, 40000),
                    "tower_damage": random.randint(500, 5000),
                    "hero_healing": random.randint(0, 5000),
                },
            )

        for slot_idx, player in enumerate(dire_players):
            steam_id_64 = player.steamid or (
                player.steam_account_id + CustomUser.STEAM_ID_64_BASE
                if player.steam_account_id
                else None
            )
            PlayerMatchStats.objects.update_or_create(
                match=match,
                steam_id=steam_id_64,
                defaults={
                    "user": player,
                    "player_slot": 128 + slot_idx,  # Dire slots start at 128
                    "hero_id": random.randint(1, 130),
                    "kills": random.randint(2, 15),
                    "deaths": random.randint(1, 10),
                    "assists": random.randint(5, 25),
                    "gold_per_min": random.randint(300, 600),
                    "xp_per_min": random.randint(400, 700),
                    "last_hits": random.randint(50, 300),
                    "denies": random.randint(0, 20),
                    "hero_damage": random.randint(10000, 40000),
                    "tower_damage": random.randint(500, 5000),
                    "hero_healing": random.randint(0, 5000),
                },
            )

        matches_created += 1
        print(
            f"  Created match {match_id} (tier: {config['tier']}, players: {len(radiant_players) + len(dire_players)})"
        )

    print(
        f"Created tournament '{TOURNAMENT_NAME}' with {len(games)} games and {matches_created} unlinked Steam matches"
    )

    # Flush Redis cache
    _flush_redis_cache()

    return tournament


def populate_bracket_unset_winner_tournament(force=False):
    """
    Create dedicated tournament for bracket unset winner E2E test.

    Uses data from tests/data/tournaments.py and tests/data/teams.py for
    consistent, maintainable test data.

    Creates a 4-team double elimination tournament with:
    - All games in 'pending' status (no completed games)
    - Teams assigned to first round games
    - Bracket links set up for winner/loser advancement

    This tournament is used exclusively by the bracket unset winner test
    to avoid polluting or being affected by other tests.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from app.models import Game, League, Team, Tournament
    from tests.data.teams import BRACKET_UNSET_WINNER_TEAMS
    from tests.data.tournaments import BRACKET_UNSET_WINNER_TOURNAMENT

    tournament_config = BRACKET_UNSET_WINNER_TOURNAMENT
    team_configs = BRACKET_UNSET_WINNER_TEAMS

    # Get the DTX league
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    if not dtx_league:
        print("DTX League not found. Run populate_organizations_and_leagues first.")
        return None

    existing = Tournament.objects.filter(name=tournament_config.name).first()
    if existing and not force:
        print(
            f"Tournament '{tournament_config.name}' already exists. Use force=True to recreate."
        )
        return existing

    if force and existing:
        print(f"Deleting existing tournament '{tournament_config.name}'...")
        existing.delete()

    print(f"Creating '{tournament_config.name}' for bracket unset winner test...")

    # Create tournament using config data
    tournament = Tournament.objects.create(
        name=tournament_config.name,
        date_played=date.today(),
        state=tournament_config.state,
        tournament_type=tournament_config.tournament_type,
        league=dtx_league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )

    # Collect all users for this tournament
    all_users = []
    teams = []

    for team_config in team_configs:
        # Get users by username from database
        team_members = []
        for member in team_config.members:
            user = CustomUser.objects.filter(username=member.username).first()
            if user:
                team_members.append(user)
            else:
                print(f"  Warning: User '{member.username}' not found")

        if not team_members:
            print(f"  Warning: No members found for team '{team_config.name}'")
            continue

        # Get captain
        captain = CustomUser.objects.filter(
            username=team_config.captain.username
        ).first()
        if not captain and team_members:
            captain = team_members[0]

        team = Team.objects.create(
            tournament=tournament,
            name=team_config.name,
            captain=captain,
            draft_order=team_config.draft_order or len(teams) + 1,
        )
        team.members.set(team_members)
        teams.append(team)
        all_users.extend(team_members)

    tournament.users.set(all_users)

    team_names = [t.name for t in teams]
    print(f"  Created {len(teams)} teams: {', '.join(team_names)}")

    # Create bracket games (6 games for 4-team double elimination)
    # All games are PENDING - no completed games
    bracket_structure = [
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 0,
            "radiant": teams[0] if len(teams) > 0 else None,
            "dire": teams[1] if len(teams) > 1 else None,
        },
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 1,
            "radiant": teams[2] if len(teams) > 2 else None,
            "dire": teams[3] if len(teams) > 3 else None,
        },
        {"round": 1, "bracket_type": "losers", "position": 0},
        {"round": 2, "bracket_type": "winners", "position": 0},
        {"round": 2, "bracket_type": "losers", "position": 0},
        {"round": 1, "bracket_type": "grand_finals", "position": 0},
    ]

    games = []
    for bracket_info in bracket_structure:
        game = Game.objects.create(
            tournament=tournament,
            round=bracket_info["round"],
            bracket_type=bracket_info["bracket_type"],
            position=bracket_info["position"],
            elimination_type="double",
            radiant_team=bracket_info.get("radiant"),
            dire_team=bracket_info.get("dire"),
            status="pending",
        )
        games.append(game)

    # Set up bracket links for winner/loser advancement
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
        f"Created '{tournament_config.name}' with {len(teams)} teams and {len(games)} pending bracket games"
    )

    _flush_redis_cache()

    return tournament
