import random
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.db import models, transaction

from app.models import CustomUser, PositionsModel, Team

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
    Creates 5 tournaments with 20, 30, 25, 35, 40 random users respectively.

    Args:
        force (bool): If True, create tournaments even if some already exist.
    """
    from app.models import Tournament

    # Check if tournaments already exist
    existing_tournaments = Tournament.objects.count()
    if existing_tournaments >= 5 and not force:
        print(
            f"Database already has {existing_tournaments} tournaments (>=5). Use force=True to create anyway."
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

    # Tournament configurations
    tournament_configs = [
        {"name": "Spring Championship", "users": 20, "type": "double_elimination"},
        {"name": "Summer League", "users": 30, "type": "single_elimination"},
        {"name": "Autumn Cup", "users": 25, "type": "swiss"},
        {"name": "Winter Tournament", "users": 35, "type": "double_elimination"},
        {"name": "Grand Masters", "users": 40, "type": "single_elimination"},
    ]

    tournaments_created = 0

    for i, config in enumerate(tournament_configs):
        tournament_name = config["name"]
        user_count = config["users"]
        tournament_type = config["type"]

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
            # Create tournament
            tournament = Tournament.objects.create(
                name=tournament_name,
                date_played=tournament_date,
                state=state,
                tournament_type=tournament_type,
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

            # Create teams (4 teams of 5 for bracket testing)
            team_names = ["Team Alpha", "Team Beta", "Team Gamma", "Team Delta"]
            team_size = 5

            # Get users with Steam IDs for team membership
            users_for_teams = users_with_steam[
                :20
            ]  # Need 20 users (4 teams * 5 players)

            if len(users_for_teams) >= 20:
                for team_idx, team_name in enumerate(team_names):
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
                    team.save()

            tournament.save()

            team_count = tournament.teams.count()
            print(
                f"Created tournament '{tournament_name}' with {len(selected_users)} users, "
                f"{team_count} teams (type: {tournament_type}, state: {state})"
            )
            tournaments_created += 1

    print(
        f"Created {tournaments_created} new tournaments. Total tournaments in database: {Tournament.objects.count()}"
    )


def populate_steam_matches(force=False):
    """
    Generate and save mock Steam matches for test tournaments.
    Also creates bracket Game objects linked to the Steam matches.
    Uses actual team rosters to ensure Steam IDs match.

    Args:
        force: If True, delete existing mock matches and games first
    """
    from app.models import Game, Tournament
    from steam.mocks.mock_match_generator import generate_mock_matches_for_tournament
    from steam.models import Match, PlayerMatchStats

    print("Populating Steam matches and bracket games...")

    # Find a tournament with at least 4 teams
    tournament = (
        Tournament.objects.annotate(team_count=models.Count("teams"))
        .filter(team_count__gte=4)
        .first()
    )

    if not tournament:
        print("No tournament with 4+ teams found. Run populate_tournaments first.")
        return

    teams = list(tournament.teams.all()[:4])
    if len(teams) < 4:
        print(f"Tournament needs 4 teams, has {len(teams)}")
        return

    # Check for existing mock matches (IDs starting with 9000000000)
    existing_matches = Match.objects.filter(
        match_id__gte=9000000000, match_id__lt=9100000000
    )
    existing_games = Game.objects.filter(tournament=tournament)

    if existing_matches.exists() or existing_games.exists():
        if force:
            print(f"Deleting {existing_matches.count()} existing mock matches")
            print(f"Deleting {existing_games.count()} existing games")
            existing_matches.delete()
            existing_games.delete()
        else:
            print(f"Mock data already exists. Use force=True to regenerate.")
            return

    # Generate mock matches
    try:
        mock_matches = generate_mock_matches_for_tournament(tournament)
    except ValueError as e:
        print(f"Failed to generate matches: {e}")
        return

    # Define bracket structure for 4-team double elimination
    # Matches are generated in this order:
    # 0: Winners R1 Match 1 (Team0 vs Team1)
    # 1: Winners R1 Match 2 (Team2 vs Team3)
    # 2: Losers R1 (Loser0 vs Loser1)
    # 3: Winners Final (Winner0 vs Winner1)
    # 4: Losers Final (LR1Winner vs WFLoser)
    # 5: Grand Final
    # 6: Grand Final Reset (optional)

    bracket_structure = [
        {"round": 1, "bracket_type": "winners", "position": 0},  # Match 0
        {"round": 1, "bracket_type": "winners", "position": 1},  # Match 1
        {"round": 1, "bracket_type": "losers", "position": 0},  # Match 2
        {
            "round": 2,
            "bracket_type": "winners",
            "position": 0,
        },  # Match 3 (Winners Final)
        {"round": 2, "bracket_type": "losers", "position": 0},  # Match 4 (Losers Final)
        {"round": 1, "bracket_type": "grand_finals", "position": 0},  # Match 5 (GF)
        {
            "round": 2,
            "bracket_type": "grand_finals",
            "position": 0,
        },  # Match 6 (GF Reset)
    ]

    # Track winners/losers for team assignment
    match_results = []  # Will store (radiant_team, dire_team, winner, loser)

    # Save matches and create games
    saved_count = 0
    games = []

    for idx, match_data in enumerate(mock_matches):
        result = match_data["result"]

        # Save Steam Match
        match, created = Match.objects.update_or_create(
            match_id=result["match_id"],
            defaults={
                "radiant_win": result["radiant_win"],
                "duration": result["duration"],
                "start_time": result["start_time"],
                "game_mode": result["game_mode"],
                "lobby_type": result["lobby_type"],
                "league_id": 17929,  # DTX league
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

        # Determine teams for this game based on bracket position
        bracket_info = bracket_structure[idx]
        radiant_win = result["radiant_win"]

        if idx == 0:  # Winners R1 Match 1
            radiant_team, dire_team = teams[0], teams[1]
        elif idx == 1:  # Winners R1 Match 2
            radiant_team, dire_team = teams[2], teams[3]
        elif idx == 2:  # Losers R1
            radiant_team = match_results[0][3]  # Loser of match 0
            dire_team = match_results[1][3]  # Loser of match 1
        elif idx == 3:  # Winners Final
            radiant_team = match_results[0][2]  # Winner of match 0
            dire_team = match_results[1][2]  # Winner of match 1
        elif idx == 4:  # Losers Final
            radiant_team = match_results[2][2]  # Winner of Losers R1
            dire_team = match_results[3][3]  # Loser of Winners Final
        elif idx == 5:  # Grand Final
            radiant_team = match_results[3][2]  # Winner of Winners Final
            dire_team = match_results[4][2]  # Winner of Losers Final
        elif idx == 6:  # Grand Final Reset
            radiant_team = match_results[3][2]  # Winner of Winners Final
            dire_team = match_results[4][2]  # Winner of Losers Final

        winner = radiant_team if radiant_win else dire_team
        loser = dire_team if radiant_win else radiant_team
        match_results.append((radiant_team, dire_team, winner, loser))

        # Create Game object (bracket slot)
        game = Game.objects.create(
            tournament=tournament,
            round=bracket_info["round"],
            bracket_type=bracket_info["bracket_type"],
            position=bracket_info["position"],
            radiant_team=radiant_team,
            dire_team=dire_team,
            winning_team=winner,
            gameid=result["match_id"],
            status="completed",
        )
        games.append(game)
        saved_count += 1
        print(f"Saved match {result['match_id']} -> Game {game.pk}")

    # Set up next_game links for bracket flow
    if len(games) >= 6:
        # Winners R1 → Winners Final
        games[0].next_game = games[3]
        games[0].next_game_slot = "radiant"
        games[0].save()

        games[1].next_game = games[3]
        games[1].next_game_slot = "dire"
        games[1].save()

        # Winners R1 losers → Losers R1
        # (losers flow handled implicitly by team assignment)

        # Losers R1 → Losers Final
        games[2].next_game = games[4]
        games[2].next_game_slot = "radiant"
        games[2].save()

        # Winners Final winner → Grand Final
        games[3].next_game = games[5]
        games[3].next_game_slot = "radiant"
        games[3].save()

        # Winners Final loser → Losers Final
        # (handled by team assignment)

        # Losers Final → Grand Final
        games[4].next_game = games[5]
        games[4].next_game_slot = "dire"
        games[4].save()

        # Grand Final → Grand Final Reset (if exists)
        if len(games) >= 7:
            games[5].next_game = games[6]
            games[5].save()

    print(
        f"Populated {saved_count} mock Steam matches and Games for tournament '{tournament.name}'"
    )


def populate_all(force=False):
    """Run all population functions."""
    populate_users(force)
    populate_tournaments(force)
    populate_steam_matches(force)
