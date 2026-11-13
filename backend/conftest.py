"""pytest-django setup matching BackendDiscoverRunner (backend/backend/test_runner.py)."""

import os
from collections.abc import Iterator

import pytest
from django.test.utils import override_settings

from backend.test_runner import (
    DOTA_LOBBY_ENV_PREFIX,
    assign_isolated_db_names,
    default_dota_lobby_settings,
    remove_isolated_db_files,
    remove_stale_isolated_dbs,
)


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    django_db_modify_db_settings_parallel_suffix: None, django_db_keepdb: bool
) -> Iterator[None]:
    """Same temp-file test DB as BackendDiscoverRunner.setup_databases."""
    remove_stale_isolated_dbs()
    names = assign_isolated_db_names(django_db_keepdb)
    yield
    if not django_db_keepdb:
        for name in names:
            remove_isolated_db_files(name)


@pytest.fixture(scope="session", autouse=True)
def default_dota_lobby() -> Iterator[None]:
    """Same DOTA_LOBBY_* defaults as BackendDiscoverRunner.setup_test_environment."""
    saved_env = {
        key: os.environ.pop(key)
        for key in list(os.environ)
        if key.startswith(DOTA_LOBBY_ENV_PREFIX)
    }
    with override_settings(**default_dota_lobby_settings()):
        yield
    os.environ.update(saved_env)
