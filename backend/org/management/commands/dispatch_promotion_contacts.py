"""Send due promotion outbox receipts to the adaptor, once.

    python manage.py dispatch_promotion_contacts --limit 100 [--resume-paused] [--dry-run]

Run by an operator or an external scheduler; nothing schedules it here.
Prints the run report as JSON. ``--dry-run`` only counts what would be sent:
it claims no lease, changes no row and opens no connection. While
``PROMOTION_ADAPTOR_ENABLED`` is off nothing is sent and every row keeps its
state. ``--resume-paused`` moves paused rows (adaptor writeback disabled,
dry-run or a rejected credential) back to pending first; nothing else does.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from org.integration.dispatch import dispatch_due, preview_due

MAX_LIMIT = 1000


class Command(BaseCommand):
    help = "Send due promotion contact receipts to the sfg-adapter."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--resume-paused", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        if not 1 <= limit <= MAX_LIMIT:
            raise CommandError(f"--limit must be between 1 and {MAX_LIMIT}")
        kwargs = {"limit": limit, "resume_paused": options["resume_paused"]}
        if options["dry_run"]:
            report = preview_due(**kwargs)
        else:
            report = dispatch_due(**kwargs)
            if not report.enabled:
                self.stderr.write(
                    "Promotion adaptor dispatch is disabled "
                    "(PROMOTION_ADAPTOR_ENABLED); nothing was sent."
                )
        self.stdout.write(json.dumps(report.as_dict(), sort_keys=True))
