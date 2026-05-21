from django.urls import path

from common.utils import isTestEnvironment

from .test_auth import (
    bulk_rsvp_for_event,
    create_claim_request,
    create_claimable_user,
    generate_events,
    get_tournament_by_key,
    get_user_org_membership,
    kill_draft_websocket,
    login_admin,
    login_as_discord_id,
    login_as_user,
    login_event_league_staff,
    login_league_admin,
    login_league_staff,
    login_org_admin,
    login_org_staff,
    login_staff,
    login_user,
    login_user_claimer,
    reset_events_data,
    reset_events_demo,
    reset_org_admin_team,
    reset_tournament_by_key,
    sync_discord_events_test,
)
from .test_bracket import force_mismatched_winning_team
from .test_csv import reset_csv_import
from .test_demo import generate_demo_bracket, get_demo_tournament, reset_demo_tournament
from .test_health import healthz
from .test_discord import seed_discord_members
from .test_events_discord import (
    send_test_notification,
    set_org_user_approved_mmr,
    simulate_discord_signup,
    verify_discord_messages,
)
from .test_herodraft import (
    force_herodraft_timeout,
    get_herodraft_by_key,
    reset_herodraft,
    warp_herodraft_round,
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
    # Event-only League Staff (staff of league 7, never of org 7)
    path(
        "login-event-league-staff/",
        login_event_league_staff,
        name="login-event-league-staff",
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
        "reset-tournament/<str:key>/",
        reset_tournament_by_key,
        name="test-reset-tournament",
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
        "org/<int:org_pk>/user/<int:user_pk>/set-approved-mmr/",
        set_org_user_approved_mmr,
        name="test-set-org-user-approved-mmr",
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
        "herodraft/<int:draft_pk>/warp/",
        warp_herodraft_round,
        name="test-herodraft-warp",
    ),
    path(
        "herodraft-by-key/<str:key>/",
        get_herodraft_by_key,
        name="test-herodraft-by-key",
    ),
    # Team draft WebSocket testing
    path(
        "kill-draft-ws/<int:draft_id>/",
        kill_draft_websocket,
        name="test-draft-kill-ws",
    ),
    # CSV import reset
    path(
        "csv-import/reset/",
        reset_csv_import,
        name="test-csv-import-reset",
    ),
    # Discord member cache seeding
    path(
        "discord/<int:org_id>/seed-members/",
        seed_discord_members,
        name="test-seed-discord-members",
    ),
    # Events reset (preserves fixtures for E2E tests)
    path(
        "events/reset/",
        reset_events_data,
        name="reset-events",
    ),
    # Events demo reset (wipes everything for clean demo recording)
    path(
        "events/demo-reset/",
        reset_events_demo,
        name="reset-events-demo",
    ),
    # Events generation trigger (synchronous)
    path(
        "events/generate/",
        generate_events,
        name="generate-events",
    ),
    # Events bulk RSVP
    path(
        "events/<int:event_pk>/bulk-rsvp/",
        bulk_rsvp_for_event,
        name="bulk-rsvp",
    ),
    # Discord events sync (synchronous trigger)
    path(
        "events/sync-discord/",
        sync_discord_events_test,
        name="sync-discord-events",
    ),
    # Discord event lifecycle (simulate signup, verify messages, bot reactions)
    path(
        "events/<int:event_pk>/discord-signup/",
        simulate_discord_signup,
        name="simulate-discord-signup",
    ),
    path(
        "events/<int:event_pk>/discord-verify/",
        verify_discord_messages,
        name="verify-discord-messages",
    ),
    path(
        "events/<int:event_pk>/send-notification/",
        send_test_notification,
        name="send-test-notification",
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
    path("healthz/", healthz, name="test-healthz"),
    # Bracket scenario helpers (gated on TEST=true)
    path(
        "bracket/force-mismatched-winning-team/",
        force_mismatched_winning_team,
        name="test-bracket-force-mismatched-winning-team",
    ),
]
