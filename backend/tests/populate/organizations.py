"""
Organization and League population for test database.
"""

from .constants import (
    DTX_LEAGUE_NAME,
    DTX_ORG_NAME,
    DTX_STEAM_LEAGUE_ID,
    TEST_LEAGUE_NAME,
    TEST_ORG_NAME,
    TEST_STEAM_LEAGUE_ID,
)


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
            "discord_server_id": "734185035623825559",  # DTX Discord server
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
    # Set organization on league (ForeignKey)
    if dtx_league.organization != dtx_org:
        dtx_league.organization = dtx_org
        dtx_league.save()
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
    # Set organization on league (ForeignKey)
    if test_league.organization != test_org:
        test_league.organization = test_org
        test_league.save()
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
