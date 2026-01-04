import random
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.db import models, transaction

from app.models import CustomUser, PositionsModel

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
        if random.randint(0, 1):
            user.steamid = str(
                random.randint(76561197960265728, 76561197960265728 + 1000000)
            )

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
            all_users = list(CustomUser.objects.all())
            selected_users = random.sample(all_users, min(user_count, len(all_users)))

            # Add users to tournament
            tournament.users.set(selected_users)
            tournament.save()

            print(
                f"Created tournament '{tournament_name}' with {len(selected_users)} users (type: {tournament_type}, state: {state})"
            )
            tournaments_created += 1

    print(
        f"Created {tournaments_created} new tournaments. Total tournaments in database: {Tournament.objects.count()}"
    )


def populate_steam_matches(force=False):
    """
    Generate and save mock Steam matches for test tournaments.
    Uses actual team rosters to ensure Steam IDs match.

    Args:
        force: If True, delete existing mock matches first
    """
    from app.models import Tournament
    from steam.mocks.mock_match_generator import generate_mock_matches_for_tournament
    from steam.models import Match, PlayerMatchStats

    print("Populating Steam matches...")

    # Find a tournament with at least 4 teams
    tournament = (
        Tournament.objects.annotate(team_count=models.Count("teams"))
        .filter(team_count__gte=4)
        .first()
    )

    if not tournament:
        print("No tournament with 4+ teams found. Run populate_tournaments first.")
        return

    # Check for existing mock matches (IDs starting with 9000000000)
    existing = Match.objects.filter(match_id__gte=9000000000, match_id__lt=9100000000)
    if existing.exists():
        if force:
            print(f"Deleting {existing.count()} existing mock matches")
            existing.delete()
        else:
            print(
                f"Mock matches already exist ({existing.count()}). Use force=True to regenerate."
            )
            return

    # Generate mock matches
    try:
        mock_matches = generate_mock_matches_for_tournament(tournament)
    except ValueError as e:
        print(f"Failed to generate matches: {e}")
        return

    # Save to database
    saved_count = 0
    for match_data in mock_matches:
        result = match_data["result"]

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

        for player_data in result["players"]:
            # Convert 32-bit account_id back to 64-bit steam_id
            steam_id = player_data["account_id"] + 76561197960265728

            # Try to link to user via Steam ID
            user = CustomUser.objects.filter(steamid=str(steam_id)).first()

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

        saved_count += 1
        print(f"Saved match {result['match_id']}")

    print(
        f"Populated {saved_count} mock Steam matches for tournament '{tournament.name}'"
    )


def populate_all(force=False):
    """Run all population functions."""
    populate_users(force)
    populate_tournaments(force)
    populate_steam_matches(force)
