"""Single-process populate command — runs all populate functions in one Django instance."""

import time

from django.core.management.base import BaseCommand

from tests.populate import populate_all


class Command(BaseCommand):
    help = "Populate the test database with all test data in a single process."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-creation of all data even if it already exists.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        start = time.time()
        populate_all(force=force)
        elapsed = time.time() - start
        self.stdout.write(
            self.style.SUCCESS(f"populate_all completed in {elapsed:.1f}s")
        )
