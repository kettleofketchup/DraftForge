import os
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from kombu.exceptions import OperationalError

from config.celery import app as celery_app
from tests.populate.utils import without_task_publishing

UNREACHABLE_BROKER = "redis://127.0.0.1:1/0"


class WithoutTaskPublishingTest(SimpleTestCase):
    def setUp(self) -> None:
        env = patch.dict(os.environ, {"CELERY_BROKER_WRITE_URL": UNREACHABLE_BROKER})
        env.start()
        self.addCleanup(env.stop)

    def _connect(self) -> str:
        with celery_app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0)
            return conn.transport_cls

    def test_unreachable_broker_fails_outside_the_context(self) -> None:
        with self.assertRaises(OperationalError):
            self._connect()

    def test_publishes_go_to_memory_inside_the_context(self) -> None:
        with without_task_publishing():
            self.assertEqual(self._connect(), "memory")
        self.assertEqual(celery_app.conf.broker_write_url, UNREACHABLE_BROKER)

    def test_populate_commands_run_inside_the_context(self) -> None:
        seen: list[str] = []

        def record(**_: object) -> None:
            seen.append(celery_app.conf.broker_write_url)

        for command in (
            "populate_all",
            "populate_users",
            "populate_tournaments",
            "populate_test_auth_users",
        ):
            target = f"app.management.commands.{command}.{command}"
            with self.subTest(command=command), patch(target, side_effect=record):
                call_command(command, stdout=open(os.devnull, "w"))
        self.assertEqual(seen, ["memory://"] * 4)
