from django.urls import path

from common.utils import isTestEnvironment

from .test_auth import (
    create_claim_request,
    create_claimable_user,
    get_tournament_by_key,
    get_user_org_membership,
    login_admin,
    login_as_discord_id,
    login_as_user,
    login_league_admin,
    login_league_staff,
    login_org_admin,
    login_org_staff,
    login_staff,
    login_user,
    login_user_claimer,
    reset_org_admin_team,
)
from .test_csv import reset_csv_import
from .test_demo import generate_demo_bracket, get_demo_tournament, reset_demo_tournament
from .test_herodraft import (
    force_herodraft_timeout,
    get_herodraft_by_key,
    reset_herodraft,
)
from .test_steam import create_test_match

urlpatterns = [
    path(
        "login-admin/",
        login_admin,
        name="login-admin",
    ),
    path(
        "login-staff/",
        login_staff,
        name="login-staff",
    ),
    path(
        "login-user/",
        login_user,
        name="login-user",
    ),
    # User Claimer: For testing claim/merge flow (has same Steam ID as claimable_profile)
    path(
        "login-user-claimer/",
        login_user_claimer,
        name="login-user-claimer",
    ),
    # Org Admin
    path(
        "login-org-admin/",
        login_org_admin,
        name="login-org-admin",
    ),
    # Org Staff
    path(
        "login-org-staff/",
        login_org_staff,
        name="login-org-staff",
    ),
    # League Admin
    path(
        "login-league-admin/",
        login_league_admin,
        name="login-league-admin",
    ),
    # League Staff
    path(
        "login-league-staff/",
        login_league_staff,
        name="login-league-staff",
    ),
    path(
        "login-as/",
        login_as_user,
        name="login-as-user",
    ),
    path(
        "login-as-discord/",
        login_as_discord_id,
        name="test-login-as-discord",
    ),
    path(
        "tournament-by-key/<str:key>/",
        get_tournament_by_key,
        name="tournament-by-key",
    ),
    path(
        "user/<int:user_pk>/org-membership/",
        get_user_org_membership,
        name="test-user-org-membership",
    ),
    path(
        "org/<int:org_pk>/reset-admin-team/",
        reset_org_admin_team,
        name="test-reset-org-admin-team",
    ),
    path(
        "create-claimable-user/",
        create_claimable_user,
        name="test-create-claimable-user",
    ),
    path(
        "create-claim-request/",
        create_claim_request,
        name="test-create-claim-request",
    ),
    path(
        "create-match/",
        create_test_match,
        name="create-test-match",
    ),
    path(
        "herodraft/<int:draft_pk>/force-timeout/",
        force_herodraft_timeout,
        name="test-herodraft-force-timeout",
    ),
    path(
        "herodraft/<int:draft_pk>/reset/",
        reset_herodraft,
        name="test-herodraft-reset",
    ),
    path(
        "herodraft-by-key/<str:key>/",
        get_herodraft_by_key,
        name="test-herodraft-by-key",
    ),
    # CSV import reset
    path(
        "csv-import/reset/",
        reset_csv_import,
        name="test-csv-import-reset",
    ),
    # Demo tournament endpoints (for video recording)
    # More specific paths first to avoid <str:key> catching them
    path(
        "demo/bracket/<int:tournament_pk>/generate/",
        generate_demo_bracket,
        name="test-demo-bracket-generate",
    ),
    path(
        "demo/<str:key>/reset/",
        reset_demo_tournament,
        name="test-demo-reset",
    ),
    path(
        "demo/<str:key>/",
        get_demo_tournament,
        name="test-demo-get",
    ),
]
