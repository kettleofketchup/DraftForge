"""
Test Organization Configuration

This file defines the organizations used for test data.
These are created by populate_organizations_and_leagues().
"""

from tests.data.models import TestOrganization

# =============================================================================
# Main Organizations
# =============================================================================

DTX_ORG: TestOrganization = TestOrganization(
    pk=1,  # Expected PK after creation
    name="DTX",
    description="DTX - A Dota 2 amateur tournament organization.",
    rules_template="Standard DTX tournament rules apply.",
    timezone="America/New_York",
    discord_server_id="734185035623825559",
)

TEST_ORG: TestOrganization = TestOrganization(
    pk=2,  # Expected PK after creation
    name="Test Organization",
    description="Test organization for Cypress E2E tests.",
    rules_template="Test rules template.",
    timezone="America/New_York",
)

# =============================================================================
# Constants for easy access
# =============================================================================

DTX_ORG_NAME = DTX_ORG.name
TEST_ORG_NAME = TEST_ORG.name

# =============================================================================
# All Organizations (for iteration)
# =============================================================================

ALL_ORGANIZATIONS: list[TestOrganization] = [
    DTX_ORG,
    TEST_ORG,
]
