"""
Shuffle draft tie resolution test data population.

Creates an isolated organization, league, tournament, and users for
shuffle draft tie resolution E2E tests.

Infrastructure created:
- Shuffle Tie Org (pk=6) - dedicated org for shuffle tie tests
- Shuffle Tie League (pk=6, steam_league_id=17934) - under Shuffle Tie org
- Shuffle Tie Resolution Test tournament - 4 captain-only teams
- 20 shuffle tie users (pk=4000-4019) - 4 captains + 16 available players

MMR layout (captain-only teams, no pre-assigned members):
- Captain 1: 2000 MMR (lowest -> picks first, no tie)
- Captains 2-4: 3000 MMR each
- 16 available players: 2000 MMR each

After first pick (player with 2000 MMR joins Team 1):
- Team 1: 4000, Teams 2/3/4: 3000 -> 3-way tie -> tie_roll event

The site admin user (pk=1001) is added as admin of the org so E2E tests
can log in and manage the draft.
"""

from datetime import date

from app.models import (
    CustomUser,
    Draft,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from tests.data.leagues import SHUFFLE_TIE_LEAGUE
from tests.data.organizations import SHUFFLE_TIE_ORG
from tests.data.tournaments import SHUFFLE_TIE_TOURNAMENT
from tests.data.users import ADMIN_USER, SHUFFLE_TIE_CAPTAINS, SHUFFLE_TIE_PLAYERS

from .utils import ensure_league_user, ensure_org_user, flush_redis_cache


def populate_shuffle_tie_data(force=False):
    """
    Create the full shuffle tie resolution test infrastructure.

    1. Shuffle Tie Org + League (isolated from other orgs)
    2. 20 dedicated test users with controlled MMR
    3. Tournament with 4 captain-only teams
    4. Shuffle draft with rounds built
    """
    print("Populating shuffle tie resolution test data...")

    # 1. Create Shuffle Tie Organization
    org, created = Organization.objects.update_or_create(
        name=SHUFFLE_TIE_ORG.name,
        defaults={
            "description": SHUFFLE_TIE_ORG.description,
            "logo": "",
            "rules_template": SHUFFLE_TIE_ORG.rules_template,
            "timezone": SHUFFLE_TIE_ORG.timezone,
        },
    )
    print(
        f"  {'Created' if created else 'Updated'} organization: {SHUFFLE_TIE_ORG.name}"
    )

    # 2. Create Shuffle Tie League
    league, created = League.objects.update_or_create(
        steam_league_id=SHUFFLE_TIE_LEAGUE.steam_league_id,
        defaults={
            "name": SHUFFLE_TIE_LEAGUE.name,
            "description": SHUFFLE_TIE_LEAGUE.description,
            "rules": SHUFFLE_TIE_LEAGUE.rules,
            "prize_pool": "",
            "timezone": SHUFFLE_TIE_LEAGUE.timezone,
        },
    )
    if league.organization != org:
        league.organization = org
        league.save()
    print(f"  {'Created' if created else 'Updated'} league: {SHUFFLE_TIE_LEAGUE.name}")

    # Set as default league
    if org.default_league != league:
        org.default_league = league
        org.save()

    # 3. Add admin user as org admin (so E2E tests can manage draft)
    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user and admin_user not in org.admins.all():
        org.admins.add(admin_user)
        print(f"  Added {admin_user.username} as admin of {SHUFFLE_TIE_ORG.name}")

    # 4. Create dedicated test users
    all_users = []

    for user_data in SHUFFLE_TIE_CAPTAINS + SHUFFLE_TIE_PLAYERS:
        existing = CustomUser.objects.filter(pk=user_data.pk).first()
        if existing and not force:
            all_users.append(existing)
            continue

        if existing and force:
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
        all_users.append(user)

    print(f"  Created/verified {len(all_users)} shuffle tie users (pk=4000-4019)")

    # 5. Set OrgUser MMR values
    captain_mmrs = [2000, 3000, 3000, 3000]
    for user_data, mmr in zip(SHUFFLE_TIE_CAPTAINS, captain_mmrs):
        db_user = CustomUser.objects.get(pk=user_data.pk)
        org_user = ensure_org_user(db_user, org, mmr=mmr)
        ensure_league_user(db_user, org_user, league)

    for user_data in SHUFFLE_TIE_PLAYERS:
        db_user = CustomUser.objects.get(pk=user_data.pk)
        org_user = ensure_org_user(db_user, org, mmr=2000)
        ensure_league_user(db_user, org_user, league)

    # 6. Create tournament (delete existing if force)
    tournament_name = SHUFFLE_TIE_TOURNAMENT.name
    existing_tournament = Tournament.objects.filter(name=tournament_name).first()
    if existing_tournament and not force:
        print(
            f"  Tournament '{tournament_name}' already exists "
            f"(pk={existing_tournament.pk}), skipping..."
        )
        flush_redis_cache()
        return existing_tournament

    if existing_tournament:
        existing_tournament.delete()

    tournament = Tournament.objects.create(
        name=tournament_name,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=SHUFFLE_TIE_LEAGUE.steam_league_id,
    )

    # Add all 20 users to tournament
    tournament.users.set(all_users)

    # 7. Create 4 teams with CAPTAIN ONLY (no extra members)
    team_names = ["Tie Team Alpha", "Tie Team Beta", "Tie Team Gamma", "Tie Team Delta"]
    captains = [CustomUser.objects.get(pk=c.pk) for c in SHUFFLE_TIE_CAPTAINS]

    for i, (captain, name) in enumerate(zip(captains, team_names)):
        team = Team.objects.create(
            tournament=tournament,
            name=name,
            captain=captain,
            draft_order=i + 1,
        )
        team.members.set([captain])  # Captain only -- room for 4 draft picks

    # 8. Create shuffle draft (build_shuffle_rounds assigns first captain)
    draft = Draft.objects.create(
        tournament=tournament,
        draft_style="shuffle",
    )
    draft.build_rounds()

    print(
        f"  Created '{tournament_name}' (pk={tournament.pk}) -- "
        f"4 captain-only teams, MMR: [2000, 3000, 3000, 3000], "
        f"16 available players at 2000 MMR each"
    )

    flush_redis_cache()
    return tournament
