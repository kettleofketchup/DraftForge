import os
import random

import django
import requests  # Added for Discord API calls
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.utils import timezone
from faker import Faker

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.backend.settings")
from backend.app.models import CustomUser, Game, Team, Tournament

fake = Faker()


def get_discord_guild_members_data():
    """Fetches member data from the configured Discord guild."""
    guild_id = getattr(settings, "DISCORD_GUILD_ID", None)
    bot_token = getattr(settings, "DISCORD_BOT_TOKEN", None)
    # Default to v10 if not specified, as it's a common current version
    api_base_url = getattr(
        settings, "DISCORD_API_BASE_URL", "https://discord.com/api/v10"
    )

    if not guild_id or not bot_token:
        print(
            "Warning: DISCORD_GUILD_ID or DISCORD_BOT_TOKEN not configured in Django settings. Skipping real Discord user creation."
        )
        return []

    url = f"{api_base_url}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}

    all_members_data = []
    last_user_id = None
    limit = 1000  # Discord's max limit per request

    print(f"Fetching Discord members from guild {guild_id}...")
    while True:
        params = {"limit": limit}
        if last_user_id:
            params["after"] = last_user_id

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            page_data = response.json()

            if not page_data:  # No more members
                break

            all_members_data.extend(page_data)

            if len(page_data) < limit:  # Last page fetched
                break

            # Get the ID of the last user for pagination
            last_user_id = page_data[-1]["user"]["id"]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Discord members: {e}")
            return []  # Return empty list on error
        except KeyError:
            print(
                f"Error parsing Discord member data (KeyError). This might be due to an unexpected API response format."
            )
            return []
        except Exception as e:
            print(f"An unexpected error occurred while fetching Discord members: {e}")
            return []

    print(f"Fetched {len(all_members_data)} raw member entries from Discord.")
    return all_members_data


def create_users_from_discord(num_to_create=10):
    """Creates CustomUser objects from a subset of real Discord guild members."""
    discord_members_data = get_discord_guild_members_data()
    if not discord_members_data:
        print("No Discord member data fetched, cannot create users from Discord.")
        return []

    users_created = []
    # Shuffle to get a random subset if num_to_create is less than total members
    random.shuffle(discord_members_data)

    created_custom_usernames = (
        set()
    )  # To help avoid immediate collision for CustomUser.username

    for member_data in discord_members_data:
        if len(users_created) >= num_to_create:
            break

        user_info = member_data.get("user")
        if not user_info:
            # print(f"Skipping member due to missing 'user' info: {member_data}")
            continue

        discord_username_original = user_info.get("username")
        discord_id = user_info.get("id")

        if not discord_username_original or not discord_id:
            # print(f"Skipping member due to missing Discord username or ID: {user_info}")
            continue

        # For CustomUser.username, try to use discord username, but ensure uniqueness
        custom_username_candidate = discord_username_original
        suffix = 1
        while (
            CustomUser.objects.filter(username=custom_username_candidate).exists()
            or custom_username_candidate in created_custom_usernames
        ):
            custom_username_candidate = f"{discord_username_original}_{suffix}"
            suffix += 1

        created_custom_usernames.add(custom_username_candidate)

        try:
            user_data = {
                "username": custom_username_candidate,
                "first_name": member_data.get("nick", discord_username_original).split(
                    " "
                )[0]
                or "Discord",
                "last_name": "User (from Discord)",  # Indicate origin
                "email": fake.unique.email(),  # Must be unique
                "password": make_password("password123"),  # Default password
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
                "date_joined": timezone.now(),
                "steamid": None,  # Or fake: fake.random_int(min=76561197960265728, max=76561199999999999),
                "nickname": member_data.get(
                    "nick", discord_username_original
                ),  # Guild nickname or Discord username
                "mmr": None,  # Or fake: fake.random_int(min=1000, max=8000),
                "position": None,  # Or fake: str(fake.random_int(min=1, max=5)),
                "avatar": user_info.get("avatar"),  # Avatar hash
                "discordId": str(discord_id),
                "discordUsername": f"{discord_username_original}#{user_info.get('discriminator', '0000')}",
                "discordNickname": member_data.get(
                    "nick", discord_username_original
                ),  # Guild nickname or Discord username
                "guildNickname": member_data.get(
                    "nick", discord_username_original
                ),  # Guild nickname
            }
            user = CustomUser.objects.create(**user_data)
            users_created.append(user)
            # print(f"Created user from Discord: {user.username} (Discord ID: {user.discordId})")
        except IntegrityError as e:
            print(
                f"Skipping Discord user {custom_username_candidate} due to IntegrityError (likely unique email collision): {e}"
            )
            fake.unique.clear()  # Clear email provider if it collided
        except Exception as e:
            print(f"Error creating Discord user {custom_username_candidate}: {e}")

    fake.unique.clear()  # Clear unique providers for next function
    print(
        f"Attempted to create {num_to_create} users from Discord, successfully created {len(users_created)}."
    )
    return users_created


def create_users(num_users=40):
    """Creates a specified number of fake users."""
    users = []
    created_usernames = set()
    for i in range(num_users):
        while True:
            username = fake.unique.user_name()
            if (
                username not in created_usernames
                and not CustomUser.objects.filter(username=username).exists()
            ):
                created_usernames.add(username)
                break
            fake.unique.clear()  # Clear unique cache for username if collision happens often

        first_name = fake.first_name()
        last_name = fake.last_name()
        email = fake.unique.email()
        password = make_password("password123")  # Default password

        user_data = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
            "date_joined": timezone.now(),
            "steamid": fake.random_int(
                min=76561197960265728, max=76561199999999999
            ),  # Example SteamID64 range
            "nickname": fake.user_name(),
            "mmr": fake.random_int(min=1000, max=8000),
            "position": str(fake.random_int(min=1, max=5)),
            "avatar": fake.md5()[:20],  # Simulating an avatar hash
            "discordId": str(fake.random_number(digits=18, fix_len=True)),
            "discordUsername": f"{fake.user_name()}#{fake.random_number(digits=4, fix_len=True)}",
            "discordNickname": fake.user_name(),
            "guildNickname": fake.user_name(),
        }
        try:
            user = CustomUser.objects.create(**user_data)
            users.append(user)
        except IntegrityError as e:
            print(
                f"Skipping user due to IntegrityError (likely username/email collision): {e}"
            )
            fake.unique.clear()  # Clear all unique providers
        except Exception as e:
            print(f"Error creating user {username}: {e}")

    fake.unique.clear()  # Clear unique provider for next function
    return users


def create_teams(users_pool, num_teams=4):
    """Creates a specified number of fake teams."""
    teams = []
    if not users_pool:
        print("Cannot create teams without users.")
        return teams

    for i in range(num_teams):
        team_name = f"{fake.company_element()} {fake.color_name().capitalize()} {fake.animal().capitalize()}s"

        # Ensure there are users to pick a captain from
        if not users_pool:
            print(
                "Warning: No users in pool to assign as captain. Skipping team creation."
            )
            continue
        captain = random.choice(users_pool)

        team = Team.objects.create(
            name=team_name,
            captain=captain,
            current_points=fake.random_int(min=0, max=1000),
        )

        # Add members (excluding captain)
        num_members = random.randint(
            2, min(5, len(users_pool) - 1 if len(users_pool) > 1 else 0)
        )  # Ensure num_members is valid
        possible_members = [u for u in users_pool if u != captain]

        if len(possible_members) >= num_members and num_members > 0:
            members_to_add = random.sample(possible_members, num_members)
            team.members.add(*members_to_add)

        teams.append(team)
    return teams


def create_tournaments(teams_pool, users_pool, num_tournaments=2):
    """Creates a specified number of fake tournaments."""
    tournaments = []
    if not teams_pool or not users_pool:
        print("Cannot create tournaments without teams or users.")
        return tournaments

    for i in range(num_tournaments):
        tournament_name = f"{fake.bs().capitalize()} Championship {i+1}"
        date_played = fake.date_between(start_date="-30d", end_date="+90d")

        state_choice = random.choice(Tournament.STATE_CHOICES)[0]
        type_choice = random.choice(Tournament.TOURNAMNET_TYPE_CHOICES)[0]

        tournament = Tournament.objects.create(
            name=tournament_name,
            date_played=date_played,
            state=state_choice,
            tournment_type=type_choice,
        )

        if teams_pool:
            tournament.teams.add(*teams_pool)

        if users_pool:
            num_tournament_users = random.randint(
                min(10, len(users_pool)),
                min(max(10, len(users_pool)), len(users_pool)),  # Ensure valid range
            )
            if num_tournament_users > 0:
                tournament_users_to_add = random.sample(
                    users_pool, num_tournament_users
                )
                tournament.users.add(*tournament_users_to_add)

        if state_choice == "past" and teams_pool:
            tournament.winning_team = random.choice(teams_pool)
            tournament.save()

        tournaments.append(tournament)
    return tournaments


def create_games_for_tournament(tournament, num_games=16):
    """Creates a specified number of fake games for a given tournament."""
    tournament_teams = list(tournament.teams.all())
    tournament_users = list(tournament.users.all())

    if len(tournament_teams) < 2:
        print(f"Not enough teams in tournament {tournament.name} to create games.")
        return

    for i in range(num_games):
        radiant_team, dire_team = random.sample(tournament_teams, 2)
        winning_team = random.choice([radiant_team, dire_team])

        game = Game.objects.create(
            tournament=tournament,
            round=random.randint(1, 5),
            radiant=radiant_team,
            dire=dire_team,
            winning_team=winning_team,
        )

        game_users = set()
        for member in radiant_team.members.all():
            game_users.add(member)
        for member in dire_team.members.all():
            game_users.add(member)

        if tournament_users:
            num_additional_users = random.randint(0, min(5, len(tournament_users)))
            if num_additional_users > 0:
                additional_users = random.sample(tournament_users, num_additional_users)
                for user in additional_users:
                    game_users.add(user)

        if game_users:
            game.users.add(*list(game_users))

        # print(
        # f"  Created game {i+1} for {tournament.name}: {radiant_team.name} vs {dire_team.name}"
        # )


def populate_data():
    """Main function to populate all data."""
    print("Starting data population...")

    # Optional: Clear existing data
    # print("Clearing existing data (excluding superusers)...")
    # Game.objects.all().delete()
    # Tournament.objects.all().delete()
    # Team.objects.all().delete()
    # CustomUser.objects.filter(is_superuser=False, is_staff=False).delete() # Be careful
    # print("Existing data cleared.")

    # --- Create users from Discord ---
    num_discord_users_to_create = 5  # Specify how many users you want from Discord
    print(
        f"\nCreating up to {num_discord_users_to_create} users from Discord guild members..."
    )
    discord_users = create_users_from_discord(num_discord_users_to_create)
    print(f"Created {len(discord_users)} users from Discord.")

    # --- Create additional purely fake users ---
    # Aim for a total of 40 users, adjust as needed
    num_additional_fake_users = 40 - len(discord_users)
    if num_additional_fake_users < 0:
        num_additional_fake_users = 0

    print(f"\nCreating {num_additional_fake_users} additional fake users...")
    additional_fake_users = create_users(num_additional_fake_users)
    print(f"Created {len(additional_fake_users)} additional fake users.")

    all_users = discord_users + additional_fake_users
    print(f"\nTotal users in pool: {len(all_users)}.")

    if not all_users:
        print(
            "User creation failed or resulted in an empty user pool. Aborting further data population."
        )
        return

    # --- Create teams ---
    print("\nCreating teams...")
    all_teams = create_teams(all_users, num_teams=4)
    print(f"Created {len(all_teams)} teams.")

    if not all_teams:
        print(
            "Team creation failed or resulted in an empty team pool. Aborting further data population."
        )
        return

    # --- Create tournaments ---
    print("\nCreating tournaments...")
    tournaments_list = create_tournaments(all_teams, all_users, num_tournaments=2)
    print(f"Created {len(tournaments_list)} tournaments.")

    if not tournaments_list:
        print("Tournament creation failed. Aborting game creation.")
        return

    # --- Create games for each tournament ---
    print("\nCreating games for each tournament...")
    for t in tournaments_list:
        print(f"Creating games for tournament: {t.name}")
        create_games_for_tournament(t, num_games=16)

    print("\nData population complete.")


if __name__ == "__main__":
    populate_data()
