import random
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.db import models, transaction

from app.models import CustomUser, Game, PositionsModel, Team

# Dota 2 themed usernames for mock data
MOCK_USERNAMES = [
    "phantom_lancer",
    "anti_mage",
    "crystal_maiden",
    "shadow_fiend",
    "invoker",
    "pudge_master",
    "drow_ranger",
    "juggernaut",
    "faceless_void",
    "earthshaker",
    "lion_finger",
    "witch_doctor",
    "vengeful_spirit",
    "tidehunter",
    "sand_king",
    "axe_dunker",
    "sven_carry",
    "tiny_toss",
    "kunkka_boat",
    "omniknight",
    "chen_micro",
    "enchantress",
    "natures_prophet",
    "treant_protector",
    "io_wisp",
    "slark_escape",
    "lifestealer",
    "lycanthrope",
    "broodmother",
    "spectre",
    "phantom_assassin",
    "templar_assassin",
    "nyx_assassin",
    "bounty_hunter",
    "clinkz",
    "weaver_time",
    "ember_spirit",
    "storm_spirit",
    "earth_spirit",
    "void_spirit",
    "dark_willow",
    "grimstroke",
    "snapfire",
    "hoodwink",
    "dawnbreaker",
    "marci_punch",
    "primal_beast",
    "muerta_ghost",
    "ringmaster",
    "techies_boom",
    "meepo_micro",
    "arc_warden",
    "morphling",
    "terrorblade",
    "naga_siren",
    "medusa_stone",
    "gyrocopter",
    "luna_glaives",
    "chaos_knight",
    "alchemist",
    "wraith_king",
    "dragon_knight",
    "huskar_spear",
    "night_stalker",
    "doom_bringer",
    "beastmaster",
    "brewmaster",
    "magnus_skewer",
    "centaur_warrunner",
    "timbersaw",
    "bristleback",
    "tusk_punch",
    "elder_titan",
    "legion_commander",
    "phoenix_egg",
    "winter_wyvern",
    "oracle_fate",
    "shadow_demon",
    "outworld_destroyer",
    "puck_phase",
    "queen_pain",
    "death_prophet",
    "leshrac",
    "lina_fire",
    "pugna_ward",
    "necrophos",
    "bane_nightmare",
    "razor_static",
    "viper_poison",
    "venomancer",
    "windranger",
    "mirana_arrow",
    "silencer",
    "skywrath",
    "disruptor",
    "keeper_light",
    "rubick_steal",
    "jakiro_heads",
    "ancient_apparition",
    "dazzle",
    "warlock_golem",
    "visage_birds",
    "undying_zombie",
    "abaddon_shield",
    "lich_chain",
]


def generate_mock_discord_members(count=100):
    """
    Generate mock Discord member data for testing when Discord API is unavailable.
    Returns data in the same format as get_discord_members_data().
    """
    members = []
    used_usernames = set()

    for i in range(count):
        # Pick a unique username
        if i < len(MOCK_USERNAMES):
            username = MOCK_USERNAMES[i]
        else:
            username = f"player_{i}"

        if username in used_usernames:
            username = f"{username}_{i}"
        used_usernames.add(username)

        # Generate a fake Discord ID (snowflake format - 18 digit number)
        discord_id = str(100000000000000000 + i)

        member = {
            "user": {
                "id": discord_id,
                "username": username,
                "avatar": None,  # No avatar for mock users
                "discriminator": "0",
                "global_name": username.replace("_", " ").title(),
            },
            "nick": None,
            "joined_at": "2024-01-01T00:00:00.000000+00:00",
        }
        members.append(member)

    return members


def create_user(user_data):
    user, created = CustomUser.objects.get_or_create(discordId=user_data["user"]["id"])
    if not created:
        return user

    mmr = random.randint(200, 6000)
    with transaction.atomic():
        print("creating user", user_data["user"]["username"])
        user.createFromDiscordData(user_data)
        user.mmr = mmr
        positions = PositionsModel.objects.create()
        positions.carry = random.randint(0, 5)
        positions.mid = random.randint(0, 5)
        positions.offlane = random.randint(0, 5)
        positions.soft_support = random.randint(0, 5)
        positions.hard_support = random.randint(0, 5)
        positions.save()
        # All mock users get a Steam ID for testing
        user.steamid = random.randint(76561197960265728, 76561197960265728 + 1000000)

        user.positions = positions
        user.save()

    return user


from tests.test_auth import createTestStaffUser, createTestSuperUser, createTestUser

# Organization/League constants for test data
DTX_ORG_NAME = "DTX"  # Main DTX organization
DTX_LEAGUE_NAME = "DTX League"
DTX_STEAM_LEAGUE_ID = 17929  # Default Steam league ID used throughout the codebase

TEST_ORG_NAME = "Test Organization"
TEST_LEAGUE_NAME = "Test League"
TEST_STEAM_LEAGUE_ID = 17930  # Different Steam league ID for testing


def populate_organizations_and_leagues(force=False):
    """
    Creates the DTX Organization and League, plus a Test Organization and League.
    Should be run BEFORE populate_users and populate_tournaments.

    Creates:
    - DTX (Organization) with DTX League (steam_league_id=17929)
    - Test Organization with Test League (steam_league_id=17930)

    Args:
        force (bool): If True, recreate organizations even if they exist.
    """
    from app.models import League, Organization

    print("Populating organizations and leagues...")

    # Check if DTX org already exists (by name)
    dtx_org = Organization.objects.filter(name=DTX_ORG_NAME).first()
    test_org = Organization.objects.filter(name=TEST_ORG_NAME).first()

    # Also check for DTX League existence
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    test_league = League.objects.filter(steam_league_id=TEST_STEAM_LEAGUE_ID).first()

    if dtx_org and dtx_league and test_org and test_league and not force:
        print(
            f"Organizations and leagues already exist. " "Use force=True to recreate."
        )
        return dtx_org, test_org

    # Create or update DTX Organization
    dtx_org, created = Organization.objects.update_or_create(
        name=DTX_ORG_NAME,
        defaults={
            "description": "DTX - A Dota 2 amateur tournament organization.",
            "logo": "",
            "rules_template": "Standard DTX tournament rules apply.",
            "timezone": "America/New_York",  # US East default
        },
    )
    action = "Created" if created else "Updated"
    print(f"  {action} organization: {DTX_ORG_NAME}")

    # Create or update DTX League
    dtx_league, created = League.objects.update_or_create(
        steam_league_id=DTX_STEAM_LEAGUE_ID,
        defaults={
            "name": DTX_LEAGUE_NAME,
            "description": "Main DTX League for in-house tournaments.",
            "rules": "Standard DTX tournament rules apply.",
            "prize_pool": "",
            "timezone": "America/New_York",  # US East default
        },
    )
    # Add organization to league (ManyToMany)
    dtx_league.organizations.add(dtx_org)
    action = "Created" if created else "Updated"
    print(
        f"  {action} league: {DTX_LEAGUE_NAME} (steam_league_id={DTX_STEAM_LEAGUE_ID})"
    )

    # Set DTX League as default for DTX Organization
    if dtx_org.default_league != dtx_league:
        dtx_org.default_league = dtx_league
        dtx_org.save()
        print(f"  Set {DTX_LEAGUE_NAME} as default league for {DTX_ORG_NAME}")

    # Create or update Test Organization
    test_org, created = Organization.objects.update_or_create(
        name=TEST_ORG_NAME,
        defaults={
            "description": "Test organization for Cypress E2E tests.",
            "logo": "",
            "rules_template": "Test rules template.",
            "timezone": "America/New_York",  # US East default
        },
    )
    action = "Created" if created else "Updated"
    print(f"  {action} organization: {TEST_ORG_NAME}")

    # Create or update Test League
    test_league, created = League.objects.update_or_create(
        steam_league_id=TEST_STEAM_LEAGUE_ID,
        defaults={
            "name": TEST_LEAGUE_NAME,
            "description": "Test league for Cypress E2E tests.",
            "rules": "Test rules.",
            "prize_pool": "",
            "timezone": "America/New_York",  # US East default
        },
    )
    test_league.organizations.add(test_org)
    action = "Created" if created else "Updated"
    print(
        f"  {action} league: {TEST_LEAGUE_NAME} (steam_league_id={TEST_STEAM_LEAGUE_ID})"
    )

    # Set Test League as default for Test Organization
    if test_org.default_league != test_league:
        test_org.default_league = test_league
        test_org.save()
        print(f"  Set {TEST_LEAGUE_NAME} as default league for {TEST_ORG_NAME}")

    print(
        f"Organizations and leagues ready. "
        f"DTX: {dtx_org.pk}/{dtx_league.pk}, Test: {test_org.pk}/{test_league.pk}"
    )
    return dtx_org, test_org


def populate_users(force=False):
    """
    Populates the database with Discord users.
    - Grabs a random number of discord users (40-100).
    - Creates CustomUser objects for them.
    - Falls back to mock data if Discord API is unavailable (e.g., in CI).

    Args:
        force (bool): If True, populate users even if there are already more than 100 users.
    """
    current_count = CustomUser.objects.count()
    createTestStaffUser()
    createTestSuperUser()
    createTestUser()
    if current_count > 100 and not force:
        print(
            f"Database already has {current_count} users (>100). Use force=True to populate anyway."
        )
        return

    # Try to get real Discord users, fall back to mock data if unavailable
    discord_users = None
    discord_bot_token = getattr(settings, "DISCORD_BOT_TOKEN", None)

    if discord_bot_token:
        try:
            from discordbot.services.users import get_discord_members_data

            discord_users = get_discord_members_data()
            print(f"Fetched {len(discord_users)} users from Discord API")
        except Exception as e:
            print(f"Discord API unavailable: {e}")
            print("Falling back to mock data...")

    if not discord_users:
        print("Using mock Discord member data for testing")
        discord_users = generate_mock_discord_members(100)

    # Get a random sample of users
    sample_size = random.randint(40, min(100, len(discord_users)))
    users_to_create = random.sample(discord_users, sample_size)

    # Create users
    users_created = 0

    for user in users_to_create:
        create_user(user)
        users_created += 1

    print(
        f"Created {users_created} new users. Total users in database: {CustomUser.objects.count()}"
    )


from pydantic import BaseModel


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
    # Player counts match team counts (teams × 5 players per team)
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


def populate_steam_matches(force=False):
    """
    Generate and save mock Steam matches for test tournaments.
    Creates bracket Game objects with different completion states:
    - Tournament 1 (Completed Bracket Test): All 6 games completed with Steam matches
    - Tournament 2 (Partial Bracket Test): 2 games completed, 4 pending
    - Tournament 3 (Pending Bracket Test): All games pending (no completed games)

    Args:
        force: If True, delete existing mock matches and games first
    """
    from app.models import Game, Tournament
    from steam.mocks.mock_match_generator import generate_mock_matches_for_tournament
    from steam.models import Match, PlayerMatchStats

    print("Populating Steam matches and bracket games...")

    # Find tournaments with at least 4 teams
    tournaments = list(
        Tournament.objects.annotate(team_count=models.Count("teams"))
        .filter(team_count__gte=4)
        .order_by("pk")[:3]
    )

    if len(tournaments) < 3:
        print(
            f"Need 3 tournaments with 4+ teams, found {len(tournaments)}. Run populate_tournaments first."
        )
        return

    # Check for existing mock matches (IDs starting with 9000000000)
    existing_matches = Match.objects.filter(
        match_id__gte=9000000000, match_id__lt=9100000000
    )
    existing_games = Game.objects.filter(tournament__in=tournaments)

    if existing_matches.exists() or existing_games.exists():
        if force:
            print(f"Deleting {existing_matches.count()} existing mock matches")
            print(f"Deleting {existing_games.count()} existing games")
            existing_matches.delete()
            existing_games.delete()
        else:
            print(f"Mock data already exists. Use force=True to regenerate.")
            return

    # Define bracket structure for 4-team double elimination
    bracket_structure = [
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 0,
        },  # Match 0: Winners R1 M1
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 1,
        },  # Match 1: Winners R1 M2
        {"round": 1, "bracket_type": "losers", "position": 0},  # Match 2: Losers R1
        {
            "round": 2,
            "bracket_type": "winners",
            "position": 0,
        },  # Match 3: Winners Final
        {"round": 2, "bracket_type": "losers", "position": 0},  # Match 4: Losers Final
        {
            "round": 1,
            "bracket_type": "grand_finals",
            "position": 0,
        },  # Match 5: Grand Final
    ]

    # Tournament scenarios:
    # T1: All 6 games completed (indexes 0-5)
    # T2: 2 games completed (indexes 0-1), 4 pending (indexes 2-5)
    # T3: 0 games completed (all 6 pending)
    tournament_configs = [
        {
            "tournament": tournaments[0],
            "completed_count": 6,
            "match_id_base": 9000000001,
        },
        {
            "tournament": tournaments[1],
            "completed_count": 2,
            "match_id_base": 9000000101,
        },
        {
            "tournament": tournaments[2],
            "completed_count": 0,
            "match_id_base": 9000000201,
        },
    ]

    for config in tournament_configs:
        tournament = config["tournament"]
        completed_count = config["completed_count"]
        match_id_base = config["match_id_base"]

        teams = list(tournament.teams.all()[:4])
        if len(teams) < 4:
            print(
                f"Tournament '{tournament.name}' needs 4 teams, has {len(teams)}, skipping..."
            )
            continue

        # Generate mock matches only if we need completed games
        mock_matches = []
        if completed_count > 0:
            try:
                mock_matches = generate_mock_matches_for_tournament(tournament)
            except ValueError as e:
                print(f"Failed to generate matches for {tournament.name}: {e}")
                continue

        games = []
        match_results = []  # (radiant_team, dire_team, winner, loser)

        for idx, bracket_info in enumerate(bracket_structure):
            is_completed = idx < completed_count

            # Determine teams based on bracket position
            # Only assign teams to later rounds if their source games are COMPLETED
            if idx == 0:  # Winners R1 Match 1
                radiant_team, dire_team = teams[0], teams[1]
            elif idx == 1:  # Winners R1 Match 2
                radiant_team, dire_team = teams[2], teams[3]
            elif idx == 2:  # Losers R1 - needs games 0 and 1 completed
                if completed_count >= 2 and len(match_results) >= 2:
                    radiant_team = match_results[0][3]  # Loser of match 0
                    dire_team = match_results[1][3]  # Loser of match 1
                else:
                    radiant_team, dire_team = None, None
            elif idx == 3:  # Winners Final - needs games 0 and 1 completed
                if completed_count >= 2 and len(match_results) >= 2:
                    radiant_team = match_results[0][2]  # Winner of match 0
                    dire_team = match_results[1][2]  # Winner of match 1
                else:
                    radiant_team, dire_team = None, None
            elif idx == 4:  # Losers Final - needs games 2 and 3 completed
                if completed_count >= 4 and len(match_results) >= 4:
                    radiant_team = match_results[2][2]  # Winner of Losers R1
                    dire_team = match_results[3][3]  # Loser of Winners Final
                else:
                    radiant_team, dire_team = None, None
            elif idx == 5:  # Grand Final - needs games 3 and 4 completed
                if completed_count >= 5 and len(match_results) >= 5:
                    radiant_team = match_results[3][2]  # Winner of Winners Final
                    dire_team = match_results[4][2]  # Winner of Losers Final
                else:
                    radiant_team, dire_team = None, None

            # Handle completed games with Steam match data
            winner = None
            gameid = None

            if is_completed and idx < len(mock_matches):
                result = mock_matches[idx]["result"]
                gameid = match_id_base + idx
                radiant_win = result["radiant_win"]

                # Save Steam Match
                match, _ = Match.objects.update_or_create(
                    match_id=gameid,
                    defaults={
                        "radiant_win": radiant_win,
                        "duration": result["duration"],
                        "start_time": result["start_time"],
                        "game_mode": result["game_mode"],
                        "lobby_type": result["lobby_type"],
                        "league_id": DTX_STEAM_LEAGUE_ID,
                    },
                )

                # Save PlayerMatchStats
                for player_data in result["players"]:
                    steam_id = player_data["account_id"] + 76561197960265728
                    user = CustomUser.objects.filter(steamid=steam_id).first()

                    PlayerMatchStats.objects.update_or_create(
                        match=match,
                        steam_id=steam_id,
                        defaults={
                            "user": user,
                            "player_slot": player_data["player_slot"],
                            "hero_id": player_data["hero_id"],
                            "kills": player_data["kills"],
                            "deaths": player_data["deaths"],
                            "assists": player_data["assists"],
                            "gold_per_min": player_data["gold_per_min"],
                            "xp_per_min": player_data["xp_per_min"],
                            "last_hits": player_data["last_hits"],
                            "denies": player_data["denies"],
                            "hero_damage": player_data["hero_damage"],
                            "tower_damage": player_data["tower_damage"],
                            "hero_healing": player_data["hero_healing"],
                        },
                    )

                winner = radiant_team if radiant_win else dire_team
                loser = dire_team if radiant_win else radiant_team
                match_results.append((radiant_team, dire_team, winner, loser))
            # For pending games, no need to track placeholder results
            # Teams for later rounds will be determined when games are actually completed

            # Create Game object
            game = Game.objects.create(
                tournament=tournament,
                round=bracket_info["round"],
                bracket_type=bracket_info["bracket_type"],
                position=bracket_info["position"],
                elimination_type="double",  # All our test brackets are double elim
                radiant_team=radiant_team,
                dire_team=dire_team,
                winning_team=winner if is_completed else None,
                gameid=gameid,
                status="completed" if is_completed else "pending",
            )
            games.append(game)

        # Set up next_game links for bracket flow
        if len(games) >= 6:
            games[0].next_game = games[3]
            games[0].next_game_slot = "radiant"
            games[0].save()

            games[1].next_game = games[3]
            games[1].next_game_slot = "dire"
            games[1].save()

            games[2].next_game = games[4]
            games[2].next_game_slot = "radiant"
            games[2].save()

            games[3].next_game = games[5]
            games[3].next_game_slot = "radiant"
            games[3].save()

            games[4].next_game = games[5]
            games[4].next_game_slot = "dire"
            games[4].save()

            # Set up loser_next_game links for double elimination
            # Winners R1 M1 loser -> Losers R1 as radiant
            games[0].loser_next_game = games[2]
            games[0].loser_next_game_slot = "radiant"
            games[0].save()

            # Winners R1 M2 loser -> Losers R1 as dire
            games[1].loser_next_game = games[2]
            games[1].loser_next_game_slot = "dire"
            games[1].save()

            # Winners Final loser -> Losers Final as dire
            games[3].loser_next_game = games[4]
            games[3].loser_next_game_slot = "dire"
            games[3].save()

        completed_games = len([g for g in games if g.status == "completed"])
        pending_games = len([g for g in games if g.status == "pending"])
        print(
            f"Tournament '{tournament.name}': {completed_games} completed, {pending_games} pending games"
        )

    # Flush Redis cache to ensure bracket data is fresh
    _flush_redis_cache()


def _flush_redis_cache():
    """Flush Redis cache to ensure fresh data after population."""
    try:
        import redis
        from django.conf import settings

        redis_url = getattr(settings, "CACHEOPS_REDIS", None)
        if redis_url:
            # Parse redis URL or use dict config with short timeout to avoid hanging
            if isinstance(redis_url, str):
                client = redis.from_url(
                    redis_url, socket_timeout=2, socket_connect_timeout=2
                )
            else:
                # Add timeout to dict config
                config = {**redis_url, "socket_timeout": 2, "socket_connect_timeout": 2}
                client = redis.Redis(**config)
            client.flushall()
            print("Redis cache flushed successfully")
        else:
            print("No CACHEOPS_REDIS configured, skipping cache flush")
    except redis.exceptions.ConnectionError as e:
        print(f"Redis not available, skipping cache flush: {e}")
    except redis.exceptions.TimeoutError as e:
        print(f"Redis timeout, skipping cache flush: {e}")
    except Exception as e:
        print(f"Warning: Failed to flush Redis cache: {e}")


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
        steam_id = 76561197960300000 + i  # Unique steam IDs for linking

        user, created = CustomUser.objects.get_or_create(
            discordId=discord_id,
            defaults={
                "username": username,
                "steamid": steam_id,
                "mmr": 3000 + (i * 100),
            },
        )
        if created:
            # Create positions for new user
            positions = PositionsModel.objects.create(
                carry=3, mid=3, offlane=3, soft_support=3, hard_support=3
            )
            user.positions = positions
            user.save()
        elif user.steamid != steam_id:
            # Ensure steam ID is set correctly
            user.steamid = steam_id
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
            PlayerMatchStats.objects.update_or_create(
                match=match,
                steam_id=player.steamid,
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
            PlayerMatchStats.objects.update_or_create(
                match=match,
                steam_id=player.steamid,
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


def populate_real_tournament_38(force=False):
    """
    Creates test data based on real production Tournament 38.

    Tournament 38 details:
    - Name: "2026-01-18" (the date it was played)
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

    from app.models import CustomUser, Game, League, PositionsModel, Team, Tournament

    TOURNAMENT_NAME = "Real Tournament 38"

    # Get the DTX league
    dtx_league = League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).first()
    if not dtx_league:
        print(f"DTX League not found. Run populate_organizations_and_leagues first.")
        return None

    # Check if tournament already exists
    existing_tournament = Tournament.objects.filter(name=TOURNAMENT_NAME).first()

    if existing_tournament and not force:
        print(
            f"Tournament '{TOURNAMENT_NAME}' already exists. Use force=True to recreate."
        )
        return existing_tournament

    if force and existing_tournament:
        print(f"Deleting existing tournament '{TOURNAMENT_NAME}'...")
        existing_tournament.delete()

    print(f"Creating '{TOURNAMENT_NAME}' with real production data...")

    # Team structure referencing usernames from REAL_TOURNAMENT_USERS (single source of truth)
    # Only defines team composition - user data comes from REAL_TOURNAMENT_USERS
    team_structure = {
        "vrm.mtl's Team": {
            "captain": "vrm.mtl",
            "members": ["tornope", "nimstria1", "thekingauto", "leafael."],
        },
        "ethan0688_'s Team": {
            "captain": "ethan0688_",
            "members": ["just__khang", "heffdawgz", "pushingshots", "p0styp0sty"],
        },
        "benevolentgremlin's Team": {
            "captain": "benevolentgremlin",
            "members": ["clarexlauda", "creemy__", "sir_t_rex", "bearthebear"],
        },
        "gglive's Team": {
            "captain": "gglive",
            "members": ["anil98765", "hassanzulfi", "abaybay1392", "reacher_z"],
        },
    }

    def create_or_get_user(username):
        """Create or get a user from REAL_TOURNAMENT_USERS data."""
        user_data = REAL_TOURNAMENT_USERS.get(username)
        if not user_data:
            raise ValueError(f"User '{username}' not found in REAL_TOURNAMENT_USERS")

        steam_id = user_data.get("steam_id")
        mmr = user_data.get("mmr", 3000)
        discord_id = user_data.get("discord_id")
        pos_data = user_data.get("positions", {})

        # Convert Steam ID 32-bit to 64-bit if provided
        steamid_64 = 76561197960265728 + steam_id if steam_id else None

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
                carry=pos_data.get("carry", 3),
                mid=pos_data.get("mid", 3),
                offlane=pos_data.get("offlane", 3),
                soft_support=pos_data.get("soft_support", 3),
                hard_support=pos_data.get("hard_support", 3),
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
                user.positions.carry = pos_data.get("carry", user.positions.carry)
                user.positions.mid = pos_data.get("mid", user.positions.mid)
                user.positions.offlane = pos_data.get("offlane", user.positions.offlane)
                user.positions.soft_support = pos_data.get(
                    "soft_support", user.positions.soft_support
                )
                user.positions.hard_support = pos_data.get(
                    "hard_support", user.positions.hard_support
                )
                user.positions.save()
            user.save()

        return user

    # Create tournament with DTX league
    from django.utils import timezone

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.make_aware(datetime(2026, 1, 18)),  # Real tournament date
        state="past",
        tournament_type="double_elimination",
        league=dtx_league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )

    all_users = []
    teams = []
    team_order = [
        "gglive's Team",  # Draft order 1 (ID 299)
        "benevolentgremlin's Team",  # Draft order 2 (ID 300)
        "ethan0688_'s Team",  # Draft order 3 (ID 301)
        "vrm.mtl's Team",  # Draft order 4 (ID 302)
    ]

    print("  Creating users and teams...")
    for draft_order, team_name in enumerate(team_order, 1):
        structure = team_structure[team_name]

        # Create captain (data comes from REAL_TOURNAMENT_USERS)
        captain = create_or_get_user(structure["captain"])
        all_users.append(captain)

        # Create team members
        team_members = [captain]
        for member_name in structure["members"]:
            member = create_or_get_user(member_name)
            team_members.append(member)
            all_users.append(member)

        # Create team with captain
        team = Team.objects.create(
            tournament=tournament,
            name=team_name,
            captain=captain,
            draft_order=draft_order,
        )
        team.members.set(team_members)  # Captain included in members
        teams.append(team)
        print(f"    Created team: {team_name} (captain: {captain.username})")

    # Add all users to tournament
    tournament.users.set(all_users)

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
        f"Created tournament '{TOURNAMENT_NAME}' with {len(teams)} teams, "
        f"{len(all_users)} users, and {len(games)} bracket games"
    )
    print(
        f"Note: Steam matches should auto-sync from DTX League (steam_league_id={DTX_STEAM_LEAGUE_ID})"
    )

    # Flush Redis cache
    _flush_redis_cache()

    return tournament


# =============================================================================
# Demo Tournament Data (for video recording)
# =============================================================================

# Real Tournament 38 user data - shared between demo tournaments
# Updated 2026-01-29 with latest production data including Steam IDs and positions
REAL_TOURNAMENT_USERS = {
    "just__khang": {
        "steam_id": 237494518,
        "mmr": 4600,
        "discord_id": "279963469141377024",
        "positions": {
            "carry": 2,
            "mid": 3,
            "offlane": 1,
            "soft_support": 3,
            "hard_support": 5,
        },
    },
    "clarexlauda": {
        "steam_id": 150363706,
        "mmr": 2000,
        "discord_id": "990297849688391831",
        "positions": {
            "carry": 3,
            "mid": 0,
            "offlane": 0,
            "soft_support": 2,
            "hard_support": 1,
        },
    },
    "heffdawgz": {
        "steam_id": 84657820,
        "mmr": 5800,
        "discord_id": "214624382935367682",
        "positions": {
            "carry": 0,
            "mid": 1,
            "offlane": 0,
            "soft_support": 0,
            "hard_support": 0,
        },
    },
    "pushingshots": {
        "steam_id": 104427945,
        "mmr": 2725,
        "discord_id": "403758532161437706",
        "positions": {
            "carry": 3,
            "mid": 5,
            "offlane": 0,
            "soft_support": 1,
            "hard_support": 2,
        },
    },
    "anil98765": {
        "steam_id": 104151469,
        "mmr": 2000,
        "discord_id": "435984979902595083",
        "positions": {
            "carry": 0,
            "mid": 0,
            "offlane": 0,
            "soft_support": 4,
            "hard_support": 5,
        },
    },
    "tornope": {
        "steam_id": 174372053,
        "mmr": 3500,
        "discord_id": "376476737904836614",
        "positions": {
            "carry": 1,
            "mid": 0,
            "offlane": 3,
            "soft_support": 0,
            "hard_support": 0,
        },
    },
    "nimstria1": {
        "steam_id": 171468462,
        "mmr": 500,
        "discord_id": "1303996935501381632",
        "positions": {
            "carry": 0,
            "mid": 0,
            "offlane": 0,
            "soft_support": 1,
            "hard_support": 1,
        },
    },
    "creemy__": {
        "steam_id": 114010086,
        "mmr": 4400,
        "discord_id": "359131134820483083",
        "positions": {
            "carry": 1,
            "mid": 0,
            "offlane": 2,
            "soft_support": 2,
            "hard_support": 2,
        },
    },
    "ethan0688_": {
        "steam_id": 875238678,
        "mmr": 6600,
        "discord_id": "1325607754177581066",
        "positions": {
            "carry": 2,
            "mid": 1,
            "offlane": 3,
            "soft_support": 4,
            "hard_support": 5,
        },
    },
    "hassanzulfi": {
        "steam_id": 115198530,
        "mmr": 2700,
        "discord_id": "405344576480608257",
        "positions": {
            "carry": 0,
            "mid": 0,
            "offlane": 1,
            "soft_support": 2,
            "hard_support": 3,
        },
    },
    "sir_t_rex": {
        "steam_id": 93840608,
        "mmr": 4500,
        "discord_id": "158695781216288768",
        "positions": {
            "carry": 1,
            "mid": 2,
            "offlane": 3,
            "soft_support": 0,
            "hard_support": 0,
        },
    },
    "abaybay1392": {
        "steam_id": 299870746,
        "mmr": 6700,
        "discord_id": "501861539033382933",
        "positions": {
            "carry": 1,
            "mid": 1,
            "offlane": 1,
            "soft_support": 2,
            "hard_support": 2,
        },
    },
    "p0styp0sty": {
        "steam_id": 275837954,
        "mmr": 122,
        "discord_id": "556931015147520001",
        "positions": {
            "carry": 0,
            "mid": 0,
            "offlane": 0,
            "soft_support": 1,
            "hard_support": 2,
        },
    },
    "reacher_z": {
        "steam_id": 84874902,
        "mmr": 400,
        "discord_id": "1164441465959743540",
        "positions": {
            "carry": 5,
            "mid": 4,
            "offlane": 3,
            "soft_support": 2,
            "hard_support": 1,
        },
    },
    "vrm.mtl": {
        "steam_id": 151410512,
        "mmr": 6500,
        "discord_id": "764290890617192469",
        "positions": {
            "carry": 2,
            "mid": 1,
            "offlane": 3,
            "soft_support": 0,
            "hard_support": 0,
        },
    },
    "gglive": {
        "steam_id": 1101709346,
        "mmr": 9000,
        "discord_id": "584468301988757504",
        "positions": {
            "carry": 0,
            "mid": 3,
            "offlane": 0,
            "soft_support": 2,
            "hard_support": 1,
        },
    },
    "thekingauto": {
        "steam_id": 97505772,
        "mmr": 2920,
        "discord_id": "899703742012747797",
        "positions": {
            "carry": 1,
            "mid": 2,
            "offlane": 3,
            "soft_support": 0,
            "hard_support": 0,
        },
    },
    "leafael.": {
        "steam_id": 1098211999,
        "mmr": 4268,
        "discord_id": "740972649651634198",
        "positions": {
            "carry": 3,
            "mid": 0,
            "offlane": 0,
            "soft_support": 1,
            "hard_support": 3,
        },
    },
    "benevolentgremlin": {
        "steam_id": 150218787,
        "mmr": 6800,
        "discord_id": "186688726187900929",
        "positions": {
            "carry": 1,
            "mid": 0,
            "offlane": 4,
            "soft_support": 1,
            "hard_support": 4,
        },
    },
    "bearthebear": {
        "steam_id": 240083333,
        "mmr": 2600,
        "discord_id": "251396038856802305",
        "positions": {
            "carry": 1,
            "mid": 4,
            "offlane": 4,
            "soft_support": 3,
            "hard_support": 4,
        },
    },
}


def _get_or_create_demo_user(username, user_data):
    """Get or create a user for demo tournaments with real position data."""
    from app.models import CustomUser, PositionsModel

    steam_id = user_data.get("steam_id")
    steamid_64 = 76561197960265728 + steam_id if steam_id else None
    pos_data = user_data.get("positions", {})

    user = CustomUser.objects.filter(discordId=user_data["discord_id"]).first()
    if not user:
        user = CustomUser.objects.filter(username=username).first()

    if not user:
        # Create new user with real position data
        positions = PositionsModel.objects.create(
            carry=pos_data.get("carry", 3),
            mid=pos_data.get("mid", 3),
            offlane=pos_data.get("offlane", 3),
            soft_support=pos_data.get("soft_support", 3),
            hard_support=pos_data.get("hard_support", 3),
        )
        user = CustomUser.objects.create(
            discordId=user_data["discord_id"],
            username=username,
            steamid=steamid_64,
            mmr=user_data["mmr"],
            positions=positions,
        )
    else:
        # Update existing user with latest data
        if steamid_64 and user.steamid != steamid_64:
            user.steamid = steamid_64
        if user.mmr != user_data["mmr"]:
            user.mmr = user_data["mmr"]
        # Update positions if provided
        if pos_data and user.positions:
            user.positions.carry = pos_data.get("carry", user.positions.carry)
            user.positions.mid = pos_data.get("mid", user.positions.mid)
            user.positions.offlane = pos_data.get("offlane", user.positions.offlane)
            user.positions.soft_support = pos_data.get(
                "soft_support", user.positions.soft_support
            )
            user.positions.hard_support = pos_data.get(
                "hard_support", user.positions.hard_support
            )
            user.positions.save()
        user.save()

    return user


def _fetch_discord_avatars_for_users(users):
    """Fetch Discord avatars for a list of users (sync, for population only)."""
    import os

    import requests

    discord_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not discord_token:
        print("    DISCORD_BOT_TOKEN not set, skipping avatar fetch")
        return

    headers = {"Authorization": f"Bot {discord_token}"}

    for user in users:
        if not user.discordId:
            continue
        # Skip if user already has an avatar hash (not a full URL)
        # Avatar hashes are 32-char hex strings, not URLs
        if user.avatar and not user.avatar.startswith("http"):
            continue  # Already has avatar hash

        try:
            response = requests.get(
                f"https://discord.com/api/v10/users/{user.discordId}",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                avatar_hash = data.get("avatar")
                if avatar_hash:
                    # Store just the hash - avatarUrl property constructs the full URL
                    user.avatar = avatar_hash
                    user.save(update_fields=["avatar"])
                    print(f"    Fetched avatar for {user.username}")
        except Exception as e:
            print(f"    Failed to fetch avatar for {user.username}: {e}")


def populate_demo_herodraft_tournament(force=False):
    """
    Create Demo HeroDraft Tournament for video recording.

    Creates a tournament with 2 teams (5 players each) for hero draft demos.
    Uses Real Tournament 38 users with Discord avatars.

    Args:
        force: If True, recreate the tournament even if it exists
    """
    from django.utils import timezone

    from app.models import CustomUser, Game, HeroDraft, League, Team, Tournament

    TOURNAMENT_NAME = "Demo HeroDraft Tournament"

    # Get the DTX league
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

    print(f"Creating '{TOURNAMENT_NAME}' for hero draft demos...")

    # Use first 10 Real Tournament users (2 teams of 5)
    team_a_usernames = ["vrm.mtl", "tornope", "nimstria1", "thekingauto", "clarexlauda"]
    team_b_usernames = [
        "ethan0688_",
        "just__khang",
        "heffdawgz",
        "pushingshots",
        "anil98765",
    ]

    team_a_users = [
        _get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in team_a_usernames
    ]
    team_b_users = [
        _get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in team_b_usernames
    ]
    all_users = team_a_users + team_b_users

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    _fetch_discord_avatars_for_users(all_users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="in_progress",
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(all_users)

    # Create teams
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
    from app.models import DraftTeam

    herodraft = HeroDraft.objects.create(
        game=game,
        state="waiting_for_captains",
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

    print(f"Created '{TOURNAMENT_NAME}' with 2 teams, HeroDraft ready")
    _flush_redis_cache()

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

    from app.models import CustomUser, Draft, League, Tournament

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
    users = [_get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    _fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="future",  # Before draft
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

    # Create draft for this tournament (shuffle mode for demo)
    draft = Draft.objects.create(
        tournament=tournament,
        draft_style="shuffle",
    )

    print(f"Created '{TOURNAMENT_NAME}' with 16 players, Draft ready")
    _flush_redis_cache()

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

    from app.models import CustomUser, Draft, League, Team, Tournament

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
    users = [_get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    _fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="in_progress",  # Ready for drafting
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

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
    _flush_redis_cache()

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

    from app.models import CustomUser, Draft, League, Team, Tournament

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
    users = [_get_or_create_demo_user(u, REAL_TOURNAMENT_USERS[u]) for u in usernames]

    # Fetch Discord avatars
    print("  Fetching Discord avatars...")
    _fetch_discord_avatars_for_users(users)

    tournament = Tournament.objects.create(
        name=TOURNAMENT_NAME,
        date_played=timezone.now(),
        state="in_progress",  # Ready for drafting
        tournament_type="double_elimination",
        league=dtx_league,
    )
    tournament.users.set(users)

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
    _flush_redis_cache()

    return tournament


def populate_demo_tournaments(force=False):
    """Create all demo tournaments for video recording."""
    populate_demo_herodraft_tournament(force)
    populate_demo_captaindraft_tournament(force)
    populate_demo_snake_draft_tournament(force)
    populate_demo_shuffle_draft_tournament(force)


def populate_all(force=False):
    """Run all population functions in the correct order."""
    populate_organizations_and_leagues(force)
    populate_users(force)
    populate_real_tournament_38(force)  # MOVED FIRST - gets pk 1
    populate_tournaments(force)
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
    populate_demo_tournaments(force)  # Demo data for video recording
