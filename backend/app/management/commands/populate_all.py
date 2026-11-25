"""Single-process populate command — runs all populate functions in one Django instance."""

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from tests.populate import populate_all
from tests.populate.utils import without_task_publishing


class Command(BaseCommand):
    help = "Populate the test database with all test data in a single process."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-creation of all data even if it already exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        force = options["force"]
        start = time.time()
        with without_task_publishing():
            populate_all(force=force)
        elapsed = time.time() - start
        self.stdout.write(
            self.style.SUCCESS(f"populate_all completed in {elapsed:.1f}s")
        )
