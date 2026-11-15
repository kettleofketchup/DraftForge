"""Path-based discovery (bare `manage.py test`) must name modules from backend/.

The image has /app/__init__.py and /app/backend/__init__.py, so unittest walks
the top-level directory up to / and imports `app.backend...`, which fails.
"""

import contextvars
import json
import multiprocessing
import os
import pickle
import sqlite3
import sys
import tempfile
import time
import unittest
from collections.abc import Iterator
from multiprocessing.reduction import ForkingPickler
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from cacheops.conf import settings as cacheops_settings
from django.conf import settings
from django.core.cache import caches
from django.db.backends.sqlite3.creation import DatabaseCreation
from django.db.utils import ConnectionHandler
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner, RemoteTestResult
from django.test.utils import get_runner

from backend.test_runner import (
    KEEPDB_TEST_DB_NAME,
    STALE_TEST_DB_SECONDS,
    BackendDiscoverRunner,
    checkpoint_before_clone,
    init_worker,
    isolated_db_name,
    remove_isolated_db_files,
    remove_stale_isolated_dbs,
    setup_worker_connection,
)
from config.dota_lobby import DotaLobbyConfig

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _test_ids(suite: unittest.TestSuite) -> Iterator[str]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _test_ids(item)
        else:
            yield item.id()


class TestRunnerDiscoveryTests(SimpleTestCase):
    def test_path_label_discovers_importable_module_names(self) -> None:
        runner = get_runner(settings)(verbosity=0, interactive=False)
        suite = runner.build_suite([str(BACKEND_ROOT / "app" / "tests")])
        ids = list(_test_ids(suite))
        self.assertIn(
            "app.tests.test_test_runner.TestRunnerDiscoveryTests."
            "test_path_label_discovers_importable_module_names",
            ids,
        )
        failed = [i for i in ids if i.startswith("unittest.loader._FailedTest")]
        self.assertEqual(failed, [])


class DotaLobbyDefaultsTests(SimpleTestCase):
    """The test stack turns dota_lobby on; unit tests start with it off."""

    def test_lobbies_are_off_whatever_the_environment_says(self) -> None:
        self.assertFalse(settings.DOTA_LOBBY_ENABLED)
        self.assertEqual(settings.DOTA_LOBBY_URL, "")
        self.assertEqual(settings.DOTA_LOBBY_API_KEY, "")
        self.assertEqual(settings.DOTA_LOBBY_WEBHOOK_SECRETS, ())
        self.assertEqual([k for k in os.environ if k.startswith("DOTA_LOBBY_")], [])
        self.assertFalse(DotaLobbyConfig.from_env().is_configured)

    def test_runner_restores_the_environment(self) -> None:
        runner = BackendDiscoverRunner(verbosity=0, interactive=False)
        with (
            mock.patch.dict(
                os.environ, {"DOTA_LOBBY_ENABLED": "true", "DOTA_LOBBY_URL": "http://x"}
            ),
            mock.patch("django.test.runner.setup_test_environment"),
            mock.patch("django.test.runner.teardown_test_environment"),
        ):
            runner.setup_test_environment()
            self.assertNotIn("DOTA_LOBBY_URL", os.environ)
            self.assertFalse(settings.DOTA_LOBBY_ENABLED)
            runner.teardown_test_environment()
            self.assertEqual(os.environ["DOTA_LOBBY_URL"], "http://x")


def _fake_sqlite_connection(name: str, test_name: str | None = None) -> SimpleNamespace:
    connection = SimpleNamespace(
        alias="default",
        vendor="sqlite",
        settings_dict={"NAME": name, "TEST": {"NAME": test_name}},
        close=mock.Mock(),
    )
    connection.creation = DatabaseCreation(connection)
    return connection


class IsolatedTestDbTests(SimpleTestCase):
    """Test DBs are temp files unique per run, removed with their clones and sidecars."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        patcher = mock.patch(
            "backend.test_runner.isolated_db_dir", return_value=self.dir
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _touch(self, *names: str) -> list[Path]:
        paths = [self.dir / n for n in names]
        for path in paths:
            path.touch()
        return paths

    def test_names_are_unique_per_run_and_stable_for_keepdb(self) -> None:
        first, second = isolated_db_name(), isolated_db_name()
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).parent, self.dir)
        self.assertIn(f"-{os.getpid()}-", first)
        self.assertEqual(isolated_db_name(keepdb=True), isolated_db_name(keepdb=True))

    def test_removes_db_clones_and_wal_sidecars_but_not_other_runs(self) -> None:
        name = str(self.dir / "draftforge-test-1-aa.sqlite3")
        ours = self._touch(
            "draftforge-test-1-aa.sqlite3",
            "draftforge-test-1-aa.sqlite3-wal",
            "draftforge-test-1-aa.sqlite3-shm",
            "draftforge-test-1-aa_1.sqlite3",
            "draftforge-test-1-aa_1.sqlite3-wal",
        )
        theirs = self._touch(
            "draftforge-test-1-aab.sqlite3", "draftforge-test-1-aab.sqlite3-wal"
        )
        remove_isolated_db_files(name)
        self.assertEqual([p for p in ours if p.exists()], [])
        self.assertTrue(all(p.exists() for p in theirs))

    def test_stale_sweep_keeps_fresh_and_keepdb_files(self) -> None:
        stale = self._touch(
            "draftforge-test-9-old.sqlite3", "draftforge-test-9-old.sqlite3-wal"
        )
        fresh = self._touch("draftforge-test-9-new.sqlite3")
        keep = self._touch(KEEPDB_TEST_DB_NAME)
        old = time.time() - STALE_TEST_DB_SECONDS - 60
        for path in stale + keep:
            os.utime(path, (old, old))
        remove_stale_isolated_dbs()
        self.assertEqual([p for p in stale if p.exists()], [])
        self.assertTrue(all(p.exists() for p in fresh + keep))

    def test_runner_assigns_a_temp_file_and_removes_it_on_teardown(self) -> None:
        connection = _fake_sqlite_connection("main.sqlite3")
        explicit = _fake_sqlite_connection(
            "other.sqlite3", test_name="/explicit.sqlite3"
        )
        runner = BackendDiscoverRunner(verbosity=0, interactive=False)
        with (
            mock.patch("backend.test_runner.connections") as conns,
            mock.patch.object(DiscoverRunner, "setup_databases", return_value=[]),
            mock.patch.object(DiscoverRunner, "teardown_databases"),
        ):
            conns.all.return_value = [connection, explicit]
            runner.setup_databases()
            name = connection.settings_dict["TEST"]["NAME"]
            self.assertEqual(Path(name).parent, self.dir)
            self.assertEqual(
                explicit.settings_dict["TEST"]["NAME"], "/explicit.sqlite3"
            )
            files = self._touch(Path(name).name, f"{Path(name).name}-wal")
            runner.teardown_databases([])
        self.assertEqual([p for p in files if p.exists()], [])

    def test_runner_removes_files_when_setup_fails(self) -> None:
        connection = _fake_sqlite_connection("main.sqlite3")
        runner = BackendDiscoverRunner(verbosity=0, interactive=False)

        def create_then_fail(**kwargs: object) -> list[object]:
            Path(connection.settings_dict["TEST"]["NAME"]).touch()
            raise RuntimeError("migration failed")

        with (
            mock.patch("backend.test_runner.connections") as conns,
            mock.patch.object(
                DiscoverRunner, "setup_databases", side_effect=create_then_fail
            ),
        ):
            conns.all.return_value = [connection]
            with self.assertRaises(RuntimeError):
                runner.setup_databases()
        self.assertEqual(list(self.dir.iterdir()), [])


class SpawnWorkerConnectionTests(SimpleTestCase):
    """Django's sqlite spawn path assumes an in-memory source DB."""

    def test_spawn_worker_uses_its_file_clone(self) -> None:
        connection = _fake_sqlite_connection("/tmp/draftforge-test-1-aa.sqlite3")
        with (
            mock.patch("multiprocessing.get_start_method", return_value="spawn"),
            mock.patch.object(
                connection.creation, "setup_worker_connection"
            ) as django_setup,
        ):
            setup_worker_connection(connection, 2)
        django_setup.assert_not_called()
        self.assertEqual(
            connection.settings_dict["NAME"], "/tmp/draftforge-test-1-aa_2.sqlite3"
        )
        connection.close.assert_called_once()

    def test_in_memory_and_fork_keep_djangos_path(self) -> None:
        cases = [
            ("spawn", "file:memorydb_default?mode=memory&cache=shared"),
            ("fork", "/tmp/draftforge-test-1-aa.sqlite3"),
        ]
        for start_method, name in cases:
            with self.subTest(start_method=start_method):
                connection = _fake_sqlite_connection(name)
                with (
                    mock.patch(
                        "multiprocessing.get_start_method", return_value=start_method
                    ),
                    mock.patch.object(
                        connection.creation, "setup_worker_connection"
                    ) as django_setup,
                ):
                    setup_worker_connection(connection, 2)
                django_setup.assert_called_once_with(2)

    def test_runner_uses_the_patched_worker_init(self) -> None:
        self.assertIs(
            BackendDiscoverRunner.parallel_test_suite.init_worker, init_worker
        )


class ParallelPicklingTests(SimpleTestCase):
    """--parallel pickles test cases to workers and their failures back."""

    def test_worker_result_pickles_a_failure_traceback(self) -> None:
        result = RemoteTestResult()
        try:
            self.fail("boom")
        except AssertionError:
            result.addFailure(self, sys.exc_info())
        events = pickle.loads(pickle.dumps(result.events))
        self.assertEqual(events[0][0], "addFailure")

    def test_async_test_cases_can_be_sent_to_a_worker(self) -> None:
        class AsyncCase(unittest.IsolatedAsyncioTestCase):
            async def test_it(self) -> None:
                pass

        case = AsyncCase("test_it")
        sent = pickle.loads(ForkingPickler.dumps(case._asyncioTestContext))
        self.assertIsInstance(sent, contextvars.Context)


def _redis_names() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "namespace": settings.REDIS_KEY_NAMESPACE,
        "cacheops_prefix": cacheops_settings.CACHEOPS_PREFIX(None),
        "cache_key_prefix": settings.CACHES["default"].get("KEY_PREFIX"),
        "live_cache_key_prefix": caches["default"].key_prefix,
        "channel_prefix": settings.CHANNEL_LAYERS["default"]
        .get("CONFIG", {})
        .get("prefix"),
    }


def _forked_worker_redis_names() -> dict[str, Any]:
    """Fork like ParallelTestSuite does, run init_worker, report the child's names.

    os.fork, not a Pool: under --parallel this test already runs in a daemonic
    pool worker, which may not start child processes.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        status = 1
        try:
            init_worker(multiprocessing.Value("i", 0), used_aliases=set())
            os.write(write_fd, json.dumps(_redis_names()).encode())
            status = 0
        finally:
            os._exit(status)
    os.close(write_fd)
    with os.fdopen(read_fd, "rb") as pipe:
        payload = pipe.read()
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0, "forked worker failed"
    return json.loads(payload)


class ParallelWorkerRedisNamespaceTests(SimpleTestCase):
    """Fork workers each clone their own DB, so they must not share cached rows."""

    def test_forked_worker_gets_its_own_namespace(self) -> None:
        parent = _redis_names()
        worker = _forked_worker_redis_names()
        ns = worker["namespace"]

        self.assertNotEqual(worker["pid"], parent["pid"])
        self.assertTrue(ns.startswith(f"test-{worker['pid']}-"), ns)
        self.assertNotEqual(ns, parent["namespace"])
        self.assertEqual(
            worker["cacheops_prefix"],
            parent["cacheops_prefix"].removesuffix(parent["namespace"]) + ns,
        )
        self.assertEqual(
            worker["live_cache_key_prefix"], worker["cache_key_prefix"] or ""
        )
        if parent["cache_key_prefix"] is not None:
            self.assertEqual(worker["cache_key_prefix"], ns)
        if parent["channel_prefix"] is not None:
            self.assertEqual(worker["channel_prefix"], f"asgi:{ns}")

    def test_two_workers_get_different_namespaces(self) -> None:
        first = _forked_worker_redis_names()["namespace"]
        second = _forked_worker_redis_names()["namespace"]
        self.assertNotEqual(first, second)


class WalCloneTests(SimpleTestCase):
    """Django clones a file test DB for --parallel by copying only the main file."""

    databases = {"default"}

    def test_clone_includes_writes_still_in_the_wal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = str(Path(tmp) / "source.sqlite3")
            handler = ConnectionHandler(
                {
                    "default": {
                        "ENGINE": "django.db.backends.sqlite3",
                        "NAME": source,
                        "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;"},
                    }
                }
            )
            connection = handler["default"]
            try:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE migrated (id INTEGER)")
                checkpoint_before_clone(connection)
                connection.creation.clone_test_db(suffix="1", verbosity=0)
            finally:
                connection.close()

            clone = sqlite3.connect(str(Path(tmp) / "source_1.sqlite3"))
            try:
                tables = clone.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            finally:
                clone.close()
            self.assertIn(("migrated",), tables)
