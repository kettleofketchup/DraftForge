"""
User population for test database.
"""

import random

from django.conf import settings

from app.models import CustomUser

from .constants import DTX_ORG_NAME
from .utils import create_user, ensure_org_user, generate_mock_discord_members


def populate_users(force=False):
    """
    Populates the database with Discord users.
    - Grabs a random number of discord users (40-100).
    - Creates CustomUser objects for them.
    - Creates OrgUser records for DTX organization.
    - Falls back to mock data if Discord API is unavailable (e.g., in CI).

    Args:
        force (bool): If True, populate users even if there are already more than 100 users.
    """
    from app.models import Organization
    from tests.test_auth import createTestStaffUser, createTestSuperUser, createTestUser

    current_count = CustomUser.objects.count()
    createTestStaffUser()
    createTestSuperUser()
    createTestUser()
    if current_count > 100 and not force:
        print(
            f"Database already has {current_count} users (>100). Use force=True to populate anyway."
        )
        return

    # Get DTX organization for OrgUser creation
    dtx_org = Organization.objects.filter(name=DTX_ORG_NAME).first()
    if not dtx_org:
        print(
            "DTX Organization not found. Run populate_organizations_and_leagues first."
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

    # Create users with OrgUser records
    users_created = 0

    for user in users_to_create:
        create_user(user, organization=dtx_org)
        users_created += 1

    print(
        f"Created {users_created} new users. Total users in database: {CustomUser.objects.count()}"
    )


def populate_test_auth_users(force=False):
    """
    Create test users for authentication testing (Playwright/Cypress).

    Reference: docs/testing/auth/fixtures.md
    If you update these users, also update the documentation!

    These users have specific PKs defined in tests/data/users.py to ensure
    consistency between test runs.
    """
    from social_django.models import UserSocialAuth

    from app.models import League, Organization
    from tests.data.users import (
        ADMIN_USER,
        AUTH_MATRIX_LEAGUE_ADMIN_USER,
        AUTH_MATRIX_LEAGUE_STAFF_USER,
        AUTH_MATRIX_ORG_ADMIN_USER,
        AUTH_MATRIX_ORG_MEMBER_USER,
        AUTH_MATRIX_ORG_STAFF_USER,
        CLAIMABLE_USER,
        EVENT_LEAGUE_STAFF_USER,
        LEAGUE_ADMIN_USER,
        LEAGUE_STAFF_USER,
        ORG_ADMIN_USER,
        ORG_MEMBER_USER,
        ORG_STAFF_USER,
        REGULAR_USER,
        STAFF_USER,
        USER_CLAIMER,
        TestUser,
    )

    print("Creating test auth users...")

    def create_user_with_pk(user_data: TestUser, is_claimable=False):
        """Create or update a user with a specific PK."""
        pk = user_data.pk
        username = user_data.username
        discord_id = user_data.discord_id
        steam_account_id = (
            user_data.get_steam_account_id()
        )  # 32-bit Friend ID (Dotabuff)
        nickname = user_data.nickname or username
        is_staff = user_data.is_staff
        is_superuser = user_data.is_superuser
        mmr = user_data.mmr or random.randint(2000, 6000)

        # Check if user already exists with this PK
        user = CustomUser.objects.filter(pk=pk).first()

        if user:
            # Update existing user
            user.username = username
            user.discordId = discord_id
            user.discordUsername = username
            user.steam_account_id = steam_account_id
            user.nickname = nickname
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.save()
            print(f"  Updated: {nickname or username} (pk={pk})")
        else:
            # Create new user with specific PK
            user = CustomUser(
                pk=pk,
                username=username,
                discordId=discord_id,
                discordUsername=username,
                steam_account_id=steam_account_id,
                nickname=nickname,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )
            if is_claimable:
                user.set_unusable_password()
            else:
                user.set_password("cypress")
            user.save()
            print(f"  Created: {nickname or username} (pk={pk})")

        # Create social auth for users with Discord ID (so they can log in)
        if discord_id and not is_claimable:
            UserSocialAuth.objects.update_or_create(
                user=user,
                provider="discord",
                defaults={
                    "uid": discord_id,
                    "extra_data": {
                        "access_token": "test",
                        "refresh_token": "test",
                        "expires": 9999999999,
                        "sessionid": "test",
                        "csrftoken": "test",
                    },
                },
            )

        return user

    # Create site-level users
    admin = create_user_with_pk(ADMIN_USER)
    staff = create_user_with_pk(STAFF_USER)
    regular = create_user_with_pk(REGULAR_USER)

    # Create claim profile test users
    claimable = create_user_with_pk(CLAIMABLE_USER, is_claimable=True)
    claimer = create_user_with_pk(USER_CLAIMER)

    # Create org role users
    org_admin = create_user_with_pk(ORG_ADMIN_USER)
    org_staff = create_user_with_pk(ORG_STAFF_USER)
    org_member = create_user_with_pk(ORG_MEMBER_USER)

    # Create league role users
    league_admin = create_user_with_pk(LEAGUE_ADMIN_USER)
    league_staff = create_user_with_pk(LEAGUE_STAFF_USER)
    event_league_staff = create_user_with_pk(EVENT_LEAGUE_STAFF_USER)

    # Assign org/league roles
    # Org roles
    org = Organization.objects.filter(pk=ORG_ADMIN_USER.org_id or 1).first()
    if org:
        if org_admin not in org.admins.all():
            org.admins.add(org_admin)
            print(f"  Added {org_admin.username} as admin of {org.name}")
        if org_staff not in org.staff.all():
            org.staff.add(org_staff)
            print(f"  Added {org_staff.username} as staff of {org.name}")
        # Plain member: has an OrgUser row but NOT in admins/staff. The
        # permission matrix needs this to distinguish "member, no role"
        # from "unaffiliated user".
        from tests.populate.utils import ensure_org_user

        ensure_org_user(org_member, org)
        print(f"  Ensured {org_member.username} OrgUser of {org.name}")

    # League roles
    league = League.objects.filter(pk=LEAGUE_ADMIN_USER.league_id or 1).first()
    if league:
        if league_admin not in league.admins.all():
            league.admins.add(league_admin)
            print(f"  Added {league_admin.username} as admin of {league.name}")
        if league_staff not in league.staff.all():
            league.staff.add(league_staff)
            print(f"  Added {league_staff.username} as staff of {league.name}")

    # Event-specific league staff (staff of league 7 ONLY, never of org 7)
    events_league = League.objects.filter(pk=EVENT_LEAGUE_STAFF_USER.league_id).first()
    if events_league:
        if event_league_staff not in events_league.staff.all():
            events_league.staff.add(event_league_staff)
            print(f"  Added {event_league_staff.username} as staff of {events_league.name}")

    # Auth matrix users — create the CustomUser rows here (so social auth
    # is wired alongside everyone else) but defer the org/league role
    # assignments to populate_auth_matrix_data. That step runs after
    # every other isolated-org populate so the AUTH_MATRIX_ORG pk lands
    # on 8 (matching tests/data/organizations.py).
    create_user_with_pk(AUTH_MATRIX_ORG_ADMIN_USER)
    create_user_with_pk(AUTH_MATRIX_ORG_STAFF_USER)
    create_user_with_pk(AUTH_MATRIX_ORG_MEMBER_USER)
    create_user_with_pk(AUTH_MATRIX_LEAGUE_ADMIN_USER)
    create_user_with_pk(AUTH_MATRIX_LEAGUE_STAFF_USER)

    print(f"Test auth users created/updated successfully!")
