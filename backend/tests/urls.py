from django.urls import path

from common.utils import isTestEnvironment

from .test_auth import login_admin, login_staff, login_user
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
        "create-match/",
        create_test_match,
        name="create-test-match",
    ),
]
