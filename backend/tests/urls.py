from django.urls import path

from common.utils import isTestEnvironment

from .test_auth import (
    get_tournament_by_key,
    login_admin,
    login_as_discord_id,
    login_as_user,
    login_staff,
    login_user,
)
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
