import random
from datetime import date, timedelta

import pytest
from django.db import transaction

from app.models import CustomUser, PositionsModel


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

    from discordbot.services.users import get_discord_members_data

    # Get discord users
    discord_users = get_discord_members_data()

    # Get a random sample of users
    sample_size = random.randint(40, min(100, len(discord_users)))
    users_to_create = random.sample(discord_users, sample_size)

    # Create users
    users_created = 0

    print(
        f"Created {users_created} new users. Total users in database: {CustomUser.objects.count()}"
    )
    for user in users_to_create:
        create_user(user)
        users_created += 1
    # Note: Removing the assert as it may fail when some users already exist
    # assert CustomUser.objects.count() == sample_size + 1


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
