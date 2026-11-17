from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from app.cache_utils import invalidate_model
from events.line_backfill import backfill_signup_line
from events.models import EventSignup


class Command(BaseCommand):
    help = "Stamp line position on unstamped signups and add missing backfilled ledger entries."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            result = backfill_signup_line(apps)
        if result.signups_stamped > 0:
            invalidate_model(EventSignup)
        self.stdout.write(
            f"events={result.events} signups_stamped={result.signups_stamped} "
            f"ledger_entries={result.ledger_entries} rerun={result.rerun}"
        )
