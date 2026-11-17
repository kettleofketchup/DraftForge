"""Promote waitlisted signups into seats freed by the seat-count fix (#568).

Idempotent; safe to re-run.

    python manage.py rebalance_event_waitlists --dry-run
    python manage.py rebalance_event_waitlists
"""

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from app.cache_utils import invalidate_after_commit
from events.capacity import free_seats
from events.constants import EventState, SignupStatus
from events.discord.dispatch import notify_signup_changed
from events.models import Event, EventSignup
from events.services import _promote_from_waitlist
from telemetry.logging import get_logger

log = get_logger(__name__)


def _would_promote(event: Event) -> int:
    waitlisted = (
        EventSignup.objects.nocache()
        .filter(event=event, status=SignupStatus.WAITLISTED)
        .count()
    )
    free = free_seats(event)
    return waitlisted if free is None else min(waitlisted, free)


class Command(BaseCommand):
    help = "Promote waitlisted signups into every free seat of open events."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be promoted without changing anything.",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options["dry_run"])
        events = Event.objects.nocache().filter(
            state=EventState.SIGNUPS_OPEN, max_players__isnull=False
        )
        total = 0
        for event in events.order_by("pk"):
            with transaction.atomic():
                if dry_run:
                    count = _would_promote(event)
                else:
                    count = len(_promote_from_waitlist(event))
                    invalidate_after_commit(event)
                    if count:
                        transaction.on_commit(lambda e=event: notify_signup_changed(e))
            log.info(
                "waitlist_rebalanced",
                system="events",
                subsystem="scheduling",
                event_id=event.pk,
                promoted_count=count,
                dry_run=dry_run,
            )
            if count:
                verb = "would promote" if dry_run else "promoted"
                self.stdout.write(f"{event.name} (#{event.pk}): {verb} {count}")
            total += count
        verb = "Would promote" if dry_run else "Promoted"
        self.stdout.write(self.style.SUCCESS(f"{verb} {total} signup(s)."))
