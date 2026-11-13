import multiprocessing
import os
import secrets
import tempfile
import time
from multiprocessing.sharedctypes import Synchronized
from pathlib import Path
from typing import Any, Callable

import django
import django.test.runner as django_runner
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test.runner import DiscoverRunner, ParallelTestSuite
from django.test.utils import override_settings, setup_test_environment

from config.dota_lobby import DotaLobbyConfig

BACKEND_DIR: str = str(Path(__file__).resolve().parent.parent)

DOTA_LOBBY_ENV_PREFIX = "DOTA_LOBBY_"

TEST_DB_PREFIX = "draftforge-test-"
TEST_DB_SUFFIX = ".sqlite3"
KEEPDB_TEST_DB_NAME = f"{TEST_DB_PREFIX}keepdb{TEST_DB_SUFFIX}"
STALE_TEST_DB_SECONDS = 24 * 60 * 60


def default_dota_lobby_settings() -> dict[str, Any]:
    """The DOTA_LOBBY_* settings of an environment that sets none of them."""
    config = DotaLobbyConfig.from_env({})
    return {
        "DOTA_LOBBY_ENABLED": config.enabled,
        "DOTA_LOBBY_URL": config.url,
        "DOTA_LOBBY_API_KEY": config.api_key,
        "DOTA_LOBBY_WEBHOOK_SECRETS": config.webhook_secrets,
        "DOTA_LOBBY_TIMEOUT_SECONDS": config.timeout_seconds,
        "DOTA_LOBBY_REF_PREFIX": config.ref_prefix,
        "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS": config.webhook_tolerance_seconds,
        "DOTA_LOBBY_REGION": config.region,
    }


def isolated_db_dir() -> Path:
    return Path(tempfile.gettempdir())


def isolated_db_name(keepdb: bool = False) -> str:
    """A test DB file under the temp dir, unique per run unless keepdb wants it back.

    A file, not Django's default in-memory shared-cache DB: consumer DB calls run on
    pool threads with their own connections, and shared cache fails a read of a table
    another connection is writing with "database table is locked" instead of waiting.
    """
    if keepdb:
        return str(isolated_db_dir() / KEEPDB_TEST_DB_NAME)
    token = f"{os.getpid()}-{secrets.token_hex(8)}"
    return str(isolated_db_dir() / f"{TEST_DB_PREFIX}{token}{TEST_DB_SUFFIX}")


def isolated_db_files(name: str) -> list[Path]:
    """The DB, its parallel clones (`<root>_<n>.sqlite3`) and their WAL sidecars."""
    root = Path(name)
    stem = root.name.removesuffix(TEST_DB_SUFFIX)
    return sorted(
        path
        for path in root.parent.glob(f"{stem}*")
        if path.name.startswith((f"{stem}{TEST_DB_SUFFIX}", f"{stem}_"))
    )


def remove_isolated_db_files(name: str) -> None:
    for path in isolated_db_files(name):
        path.unlink(missing_ok=True)


def remove_stale_isolated_dbs(max_age_seconds: float = STALE_TEST_DB_SECONDS) -> None:
    """Delete files a killed run left behind; a live run touches its files far more often."""
    cutoff = time.time() - max_age_seconds
    for path in isolated_db_dir().glob(f"{TEST_DB_PREFIX}*"):
        if path.name.startswith(KEEPDB_TEST_DB_NAME):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def uses_file_test_db(connection: BaseDatabaseWrapper) -> bool:
    return connection.vendor == "sqlite" and not connection.creation.is_in_memory_db(
        connection.settings_dict["NAME"] or ":memory:"
    )


def assign_isolated_db_names(keepdb: bool) -> list[str]:
    """Point every SQLite alias without an explicit TEST NAME at a temp file."""
    names: list[str] = []
    for connection in connections.all(initialized_only=False):
        test_settings = connection.settings_dict["TEST"]
        if connection.vendor != "sqlite" or test_settings.get("NAME"):
            continue
        name = isolated_db_name(keepdb)
        test_settings["NAME"] = name
        names.append(name)
    return names


def setup_worker_connection(connection: BaseDatabaseWrapper, worker_id: int) -> None:
    """Django's sqlite spawn path assumes an in-memory source DB.

    For a file DB it opens `<alias>_<n>.sqlite3` relative to the cwd, which does not
    exist, and would move the worker onto a shared-cache in-memory DB anyway. Point
    the worker at its file clone instead, as the fork path does.
    """
    if multiprocessing.get_start_method() == "spawn" and uses_file_test_db(connection):
        connection.settings_dict.update(
            connection.creation.get_test_db_clone_settings(str(worker_id))
        )
        connection.close()
        return
    connection.creation.setup_worker_connection(worker_id)


def init_worker(
    counter: Synchronized,
    initial_settings: dict[str, dict[str, Any]] | None = None,
    serialized_contents: dict[str, str] | None = None,
    process_setup: Callable[..., None] | None = None,
    process_setup_args: tuple[Any, ...] | None = None,
    debug_mode: bool | None = None,
    used_aliases: set[str] | None = None,
) -> None:
    """django.test.runner._init_worker, routing sqlite through setup_worker_connection."""
    with counter.get_lock():
        counter.value += 1
        django_runner._worker_id = counter.value
    worker_id: int = django_runner._worker_id

    start_method = multiprocessing.get_start_method()
    if start_method == "spawn":
        if process_setup and callable(process_setup):
            process_setup(*(process_setup_args or ()))
        django.setup()
        setup_test_environment(debug=debug_mode)

    for alias in used_aliases if used_aliases is not None else connections:
        connection = connections[alias]
        if start_method == "spawn":
            assert initial_settings is not None and serialized_contents is not None
            connection.settings_dict.update(initial_settings[alias])
            if value := serialized_contents.get(alias):
                connection._test_serialized_contents = value
        setup_worker_connection(connection, worker_id)


class BackendParallelTestSuite(ParallelTestSuite):
    init_worker = init_worker


class BackendDiscoverRunner(DiscoverRunner):
    """Anchor discovery at backend/ so modules import as `app.tests...`.

    backend/ and the repo root both hold an __init__.py, so unittest would
    otherwise walk the top-level directory up past backend/.

    The test stack turns dota_lobby on for Playwright (docker/.env.test), and
    the unit tests run in that stack. They start from the defaults instead,
    lobbies off and no service URL, and turn them on per test
    (lobby.tests.helpers.lobby_settings). The DOTA_LOBBY_* variables are also
    taken out of the environment, which DotaLobbyClient reads, before any
    parallel worker starts.

    SQLite test DBs are files under the temp dir (see isolated_db_name), removed with
    their clones and WAL sidecars on teardown.
    """

    parallel_test_suite = BackendParallelTestSuite

    def __init__(self, *args: Any, top_level: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, top_level=top_level or BACKEND_DIR, **kwargs)
        self._dota_lobby_env: dict[str, str] = {}
        self._dota_lobby_settings: override_settings | None = None
        self._test_db_names: list[str] = []

    def setup_test_environment(self, **kwargs: Any) -> None:
        super().setup_test_environment(**kwargs)
        self._dota_lobby_env = {
            key: os.environ.pop(key)
            for key in list(os.environ)
            if key.startswith(DOTA_LOBBY_ENV_PREFIX)
        }
        self._dota_lobby_settings = override_settings(**default_dota_lobby_settings())
        self._dota_lobby_settings.enable()

    def teardown_test_environment(self, **kwargs: Any) -> None:
        if self._dota_lobby_settings is not None:
            self._dota_lobby_settings.disable()
            self._dota_lobby_settings = None
        os.environ.update(self._dota_lobby_env)
        self._dota_lobby_env = {}
        super().teardown_test_environment(**kwargs)

    def setup_databases(self, **kwargs: Any) -> list[tuple[Any, str, bool]]:
        remove_stale_isolated_dbs()
        self._test_db_names = assign_isolated_db_names(self.keepdb)
        try:
            return super().setup_databases(**kwargs)
        except BaseException:
            self._remove_test_db_files()
            raise

    def teardown_databases(
        self, old_config: list[tuple[Any, str, bool]], **kwargs: Any
    ) -> None:
        try:
            super().teardown_databases(old_config, **kwargs)
        finally:
            self._remove_test_db_files()

    def _remove_test_db_files(self) -> None:
        if not self.keepdb:
            for name in self._test_db_names:
                remove_isolated_db_files(name)
        self._test_db_names = []
