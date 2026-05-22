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

# CSV Import Test Organization - isolated from other test data
CSV_ORG: TestOrganization = TestOrganization(
    pk=3,  # Expected PK after creation
    name="CSV Import Org",
    description="Isolated organization for CSV import E2E tests.",
    rules_template="CSV import test rules.",
    timezone="America/New_York",
)

# Demo CSV Organization - for demo video recording (separate from CSV E2E tests)
DEMO_CSV_ORG: TestOrganization = TestOrganization(
    pk=4,  # Expected PK after creation
    name="Demo CSV Org",
    description="Organization for CSV import demo video recording.",
    rules_template="Demo CSV rules.",
    timezone="America/New_York",
)

# User Edit Test Organization - isolated from other test data
USER_EDIT_ORG: TestOrganization = TestOrganization(
    pk=5,  # Expected PK after creation
    name="User Edit Org",
    description="Isolated organization for user edit E2E tests.",
    rules_template="User edit test rules.",
    timezone="America/New_York",
)

# Shuffle Tie Test Organization - isolated from other test data
SHUFFLE_TIE_ORG: TestOrganization = TestOrganization(
    pk=6,  # Expected PK after creation
    name="Shuffle Tie Org",
    description="Isolated organization for shuffle draft tie resolution E2E tests.",
    rules_template="Shuffle tie test rules.",
    timezone="America/New_York",
)

# Events E2E tests — dedicated org for event lifecycle tests
EVENTS_ORG: TestOrganization = TestOrganization(
    pk=7,
    name="Events Test Org",
    description="Isolated organization for events E2E tests.",
    timezone="America/New_York",
    discord_server_id="1467168401805017142",
)

# Auth-matrix E2E tests — isolated org used by the role-context matrix
# in frontend/tests/playwright/e2e/17-auth/. Keeping it separate from
# DTX means other suites can mutate DTX admins/staff without flapping
# the auth matrix.
AUTH_MATRIX_ORG: TestOrganization = TestOrganization(
    pk=8,
    name="Auth Matrix Test Org",
    description="Isolated organization for auth-permission matrix E2E tests.",
    rules_template="Auth matrix test rules.",
    timezone="America/New_York",
)

# =============================================================================
# Constants for easy access
# =============================================================================

DTX_ORG_NAME = DTX_ORG.name
TEST_ORG_NAME = TEST_ORG.name
CSV_ORG_NAME = CSV_ORG.name
DEMO_CSV_ORG_NAME = DEMO_CSV_ORG.name
USER_EDIT_ORG_NAME = USER_EDIT_ORG.name
SHUFFLE_TIE_ORG_NAME = SHUFFLE_TIE_ORG.name
EVENTS_ORG_NAME = EVENTS_ORG.name
AUTH_MATRIX_ORG_NAME = AUTH_MATRIX_ORG.name

# =============================================================================
# All Organizations (for iteration)
# =============================================================================

ALL_ORGANIZATIONS: list[TestOrganization] = [
    DTX_ORG,
    TEST_ORG,
    CSV_ORG,
    DEMO_CSV_ORG,
    USER_EDIT_ORG,
    SHUFFLE_TIE_ORG,
    EVENTS_ORG,
    AUTH_MATRIX_ORG,
]
