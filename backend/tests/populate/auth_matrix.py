"""
Auth-matrix test data population.

Creates an isolated organization, league, three bracket tournaments, and
five role-scoped test users for the role-context matrix in
``frontend/tests/playwright/e2e/17-auth/``. Keeping this distinct from
DTX/Test data means other suites can mutate DTX admins/staff without
flapping the matrix, and vice versa.

Infrastructure created:
- Auth Matrix Test Org (pk=8)
- Auth Matrix League (pk=9, steam_league_id=17937) under the org
- 3 tournaments under the league:
    pk=10  "Auth Matrix No Bracket"        — no bracket (Generate test)
    pk=11  "Auth Matrix Pending Bracket"   — bracket with all matches pending
    pk=12  "Auth Matrix Completed Bracket" — bracket with all matches won
- 5 auth-matrix users (pk=1090-1094) wired into the org/league roles

Runs last in ``populate_all`` so the auto-incremented org pk lands on 8.
"""

from app.models import League, Organization
from tests.data.leagues import AUTH_MATRIX_LEAGUE
from tests.data.organizations import AUTH_MATRIX_ORG
from tests.data.users import (
    AUTH_MATRIX_LEAGUE_ADMIN_USER,
    AUTH_MATRIX_LEAGUE_STAFF_USER,
    AUTH_MATRIX_ORG_ADMIN_USER,
    AUTH_MATRIX_ORG_MEMBER_USER,
    AUTH_MATRIX_ORG_STAFF_USER,
)
from tests.populate.utils import ensure_org_user


def populate_auth_matrix_data(force=False):
    """Create the auth-matrix org, league, users, and bracket tournaments."""
    from app.models import CustomUser

    print("Populating auth-matrix test data...")

    # 1. Org. Pin the pk explicitly so the matrix spec's
    # AUTH_MATRIX_ORG_PK = 8 survives anyone reordering populate steps
    # above this one — previously the pk landed by autoincrement
    # side-effect, which was fragile.
    org, created = Organization.objects.update_or_create(
        name=AUTH_MATRIX_ORG.name,
        defaults={
            "pk": AUTH_MATRIX_ORG.pk,
            "description": AUTH_MATRIX_ORG.description,
            "logo": "",
            "rules_template": AUTH_MATRIX_ORG.rules_template,
            "timezone": AUTH_MATRIX_ORG.timezone,
        },
    )
    print(f"  {'Created' if created else 'Updated'} org: {org.name} (pk={org.pk})")

    # 2. League. Same explicit-pk rationale as the org above.
    league, created = League.objects.update_or_create(
        steam_league_id=AUTH_MATRIX_LEAGUE.steam_league_id,
        defaults={
            "pk": AUTH_MATRIX_LEAGUE.pk,
            "name": AUTH_MATRIX_LEAGUE.name,
            "description": AUTH_MATRIX_LEAGUE.description,
            "rules": AUTH_MATRIX_LEAGUE.rules,
            "prize_pool": "",
            "timezone": AUTH_MATRIX_LEAGUE.timezone,
        },
    )
    if league.organization != org:
        league.organization = org
        league.save()
    print(f"  {'Created' if created else 'Updated'} league: {league.name} (pk={league.pk})")

    if org.default_league != league:
        org.default_league = league
        org.save()

    # 3. Wire users into the org/league memberships. The CustomUser rows
    # themselves were already created by populate_test_auth_users — that
    # step iterates AUTH_MATRIX_USERS via the AUTH_TEST_USERS export.
    # (Actually it doesn't yet — wire them here for self-containment.)
    org_admin = CustomUser.objects.filter(pk=AUTH_MATRIX_ORG_ADMIN_USER.pk).first()
    org_staff = CustomUser.objects.filter(pk=AUTH_MATRIX_ORG_STAFF_USER.pk).first()
    org_member = CustomUser.objects.filter(pk=AUTH_MATRIX_ORG_MEMBER_USER.pk).first()
    league_admin = CustomUser.objects.filter(pk=AUTH_MATRIX_LEAGUE_ADMIN_USER.pk).first()
    league_staff = CustomUser.objects.filter(pk=AUTH_MATRIX_LEAGUE_STAFF_USER.pk).first()

    if org_admin and org_admin not in org.admins.all():
        org.admins.add(org_admin)
        print(f"  Added {org_admin.username} as admin of {org.name}")
    if org_staff and org_staff not in org.staff.all():
        org.staff.add(org_staff)
        print(f"  Added {org_staff.username} as staff of {org.name}")
    if org_member:
        ensure_org_user(org_member, org)
        print(f"  Ensured {org_member.username} OrgUser of {org.name}")

    if league_admin and league_admin not in league.admins.all():
        league.admins.add(league_admin)
        print(f"  Added {league_admin.username} as admin of {league.name}")
    if league_staff and league_staff not in league.staff.all():
        league.staff.add(league_staff)
        print(f"  Added {league_staff.username} as staff of {league.name}")

    # 4. Bracket tournaments — delegate to the dynamic-tournament helper
    # so we get teams, captains, and (for the pending/completed variants)
    # bracket games for free.
    _create_auth_matrix_tournaments(league, force=force)

    print(f"Auth matrix data ready. Org pk={org.pk}, League pk={league.pk}")
    return org, league


def _create_auth_matrix_tournaments(league, force=False):
    """Spawn the three bracket tournaments under the Auth Matrix League.

    The no-bracket tournament gets nothing extra. The pending and
    completed variants pipe their config through the shared bracket
    helper to create six Game rows each — pending leaves them with
    no winners (so the matrix can test Set Winner), completed has all
    six with winners + linked Steam matches (so the matrix can test
    Link Steam Match).
    """
    from tests.data.tournaments import (
        AUTH_MATRIX_COMPLETED_BRACKET_CONFIG,
        AUTH_MATRIX_NO_BRACKET_CONFIG,
        AUTH_MATRIX_PENDING_BRACKET_CONFIG,
    )
    from tests.populate.steam import populate_bracket_games_for_tournament
    from tests.populate.tournaments import create_dynamic_tournament

    # Same 6-match double-elim structure used by populate_steam_matches.
    bracket_structure = [
        {"round": 1, "bracket_type": "winners", "position": 0},
        {"round": 1, "bracket_type": "winners", "position": 1},
        {"round": 1, "bracket_type": "losers", "position": 0},
        {"round": 2, "bracket_type": "winners", "position": 0},
        {"round": 2, "bracket_type": "losers", "position": 0},
        {"round": 1, "bracket_type": "grand_finals", "position": 0},
    ]

    for config in (
        AUTH_MATRIX_NO_BRACKET_CONFIG,
        AUTH_MATRIX_PENDING_BRACKET_CONFIG,
        AUTH_MATRIX_COMPLETED_BRACKET_CONFIG,
    ):
        tournament = create_dynamic_tournament(config, force=force)
        if tournament is None:
            continue
        if config is AUTH_MATRIX_NO_BRACKET_CONFIG:
            continue
        # Pending/completed get bracket Game rows + Match data.
        populate_bracket_games_for_tournament(
            tournament,
            config,
            bracket_structure,
            steam_league_id=league.steam_league_id,
        )
