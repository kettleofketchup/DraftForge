"""Delete org API connection runs past their 90-day retention.

    python manage.py cleanup_org_api_runs [--dry-run]

Checkpoints and staged pull targets go with their run; MMR values, audit
logs and deliveries are kept.
"""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from org.api_connections.orchestration import purge_expired_runs


class Command(BaseCommand):
    help = "Delete finished org API connection runs older than 90 days."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        count = purge_expired_runs(now=timezone.now(), dry_run=dry_run)
        verb = "would delete" if dry_run else "deleted"
        self.stdout.write(f"{verb} {count} runs")
