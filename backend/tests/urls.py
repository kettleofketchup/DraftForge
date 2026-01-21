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
]
