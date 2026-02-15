"""
User Edit test data population.

Creates an isolated organization, league, and tournament for user edit testing.
Also creates 3 test users that are members of the org, league, and tournament.

Infrastructure created:
- User Edit Org (pk=5) - dedicated org for user edit tests
- User Edit League (pk=5, steam_league_id=17933) - under User Edit org
- User Edit Tournament - under User Edit league, with 3 users
- 3 edit test users (pk=1050-1052) - members of the org/league/tournament
"""

from django.utils import timezone

from app.models import CustomUser, League, Organization, PositionsModel, Tournament
from tests.data.leagues import USER_EDIT_LEAGUE
from tests.data.organizations import USER_EDIT_ORG
from tests.data.tournaments import USER_EDIT_TOURNAMENT
from tests.data.users import ADMIN_USER, USER_EDIT_USERS
from tests.populate.utils import ensure_league_user, ensure_org_user


def populate_user_edit_data(force=False):
    """
    Create the full user edit test infrastructure.

    1. User Edit Org + League (isolated from other orgs)
    2. User Edit Tournament (under User Edit league)
    3. Admin user added as org admin (for E2E access)
    4. 3 edit test users as members of org/league/tournament
    """
    print("Populating user edit test data...")

    # 1. Create User Edit Organization
    edit_org, created = Organization.objects.update_or_create(
        name=USER_EDIT_ORG.name,
        defaults={
            "description": USER_EDIT_ORG.description,
            "logo": "",
            "rules_template": USER_EDIT_ORG.rules_template,
            "timezone": USER_EDIT_ORG.timezone,
        },
    )
    print(f"  {'Created' if created else 'Updated'} organization: {USER_EDIT_ORG.name}")

    # 2. Create User Edit League
    edit_league, created = League.objects.update_or_create(
        steam_league_id=USER_EDIT_LEAGUE.steam_league_id,
        defaults={
            "name": USER_EDIT_LEAGUE.name,
            "description": USER_EDIT_LEAGUE.description,
            "rules": USER_EDIT_LEAGUE.rules,
            "prize_pool": "",
            "timezone": USER_EDIT_LEAGUE.timezone,
        },
    )
    if edit_league.organization != edit_org:
        edit_league.organization = edit_org
        edit_league.save()
    print(f"  {'Created' if created else 'Updated'} league: {USER_EDIT_LEAGUE.name}")

    # Set as default league
    if edit_org.default_league != edit_league:
        edit_org.default_league = edit_league
        edit_org.save()

    # 3. Create User Edit Tournament
    edit_tournament, created = Tournament.objects.update_or_create(
        name=USER_EDIT_TOURNAMENT.name,
        defaults={
            "date_played": timezone.now(),
            "state": USER_EDIT_TOURNAMENT.state,
            "tournament_type": USER_EDIT_TOURNAMENT.tournament_type,
            "league": edit_league,
            "steam_league_id": USER_EDIT_LEAGUE.steam_league_id,
        },
    )
    print(
        f"  {'Created' if created else 'Updated'} tournament: "
        f"{USER_EDIT_TOURNAMENT.name} (pk={edit_tournament.pk})"
    )

    # 4. Add admin user as org admin (so E2E tests can edit users)
    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user and admin_user not in edit_org.admins.all():
        edit_org.admins.add(admin_user)
        print(f"  Added {admin_user.username} as admin of {USER_EDIT_ORG.name}")

    # 5. Create edit test users and add to org/league/tournament
    for user_data in USER_EDIT_USERS:
        existing = CustomUser.objects.filter(pk=user_data.pk).first()
        if existing and existing.username == user_data.username and not force:
            print(
                f"  Edit user {user_data.username} already exists (pk={user_data.pk})"
            )
            # Still ensure membership
            org_user = ensure_org_user(existing, edit_org, mmr=user_data.mmr)
            ensure_league_user(existing, org_user, edit_league)
            if existing not in edit_tournament.users.all():
                edit_tournament.users.add(existing)
            continue

        if existing:
            existing.delete()

        positions = PositionsModel.objects.create()
        user = CustomUser(
            pk=user_data.pk,
            username=user_data.username,
            nickname=user_data.nickname,
            discordId=user_data.discord_id,
            steamid=user_data.get_steam_id_64(),
            positions=positions,
        )
        user.set_unusable_password()
        user.save()
        print(f"  Created edit user: {user_data.username} (pk={user_data.pk})")

        # Add to org, league, and tournament
        org_user = ensure_org_user(user, edit_org, mmr=user_data.mmr)
        ensure_league_user(user, org_user, edit_league)
        edit_tournament.users.add(user)

    print(
        f"User edit test data ready. "
        f"Org: {edit_org.pk}, League: {edit_league.pk}, "
        f"Tournament: {edit_tournament.pk}"
    )
