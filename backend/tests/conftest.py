import os
import sys
from pathlib import Path

import pytest
from django.db.transaction import atomic
from dotenv import load_dotenv

# Add the parent directory to Python path for paths module
try:
    from paths import TEST_DB_PATH, TEST_ENV_FILE

except ModuleNotFoundError:

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from paths import TEST_DB_PATH, TEST_ENV_FILE


# Load test environment variables at module level
load_dotenv(TEST_ENV_FILE)
# Clean up test data
from django.conf import settings

try:
    from paths import TEST_DB_PATH, TEST_ENV_FILE


except ModuleNotFoundError:

    sys.path.insert(0, str(Path(__file__).parent))
    from paths import TEST_DB_PATH, TEST_ENV_FILE

from app.models import CustomUser
from tests.populate import populate_users

# @pytest.fixture(autouse=True)
# def disable_db_cleanup(request, django_db_setup, django_db_blocker):
#     # Let DB changes persist after test
#     with django_db_blocker.unblock():
#         yield


@pytest.fixture(scope="session", autouse=True)
def prerun(django_db_setup, django_db_blocker):
    """
    Override database to use a file-based SQLite for tests
    and create an admin user once per session.
    """
    # Point Django settings at the file DB
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": TEST_DB_PATH.resolve(),
        "OPTIONS": {"timeout": 30},
    }

    # Ensure database exists
    with django_db_blocker.unblock():
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()  # start fresh each run
            TEST_DB_PATH.touch()

    # Let pytest-django set up the test DB (migrations, etc.)
    django_db_setup

    # Seed admin user
    with django_db_blocker.unblock():
        user, created = CustomUser.objects.get_or_create(
            username="admin",
            email="admin@admin.com",
            defaults={"password": "admin"},
        )
        if created:
            user.set_password("admin")
            user.save()

        populate_users()

    return user
