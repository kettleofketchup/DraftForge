"""Clean up stale future events for an EventRepeater after schedule changes.

Use after fixing or changing an EventRepeater's day_of_week so that future
events generated under the previous schedule no longer pile up alongside the
new ones (see prod bug 2026-04-26 with repeater id=2).

Algorithm:
  1. Identify "stale" upcoming/signups_open events whose scheduled weekday
     does not match the repeater's current day_of_week (Sunday=0 convention).
  2. Generate fresh events on the corrected schedule via
     generate_events_for_repeater().
  3. For each stale event, find the nearest correct-day event (within 7 days)
     across upcoming/signups_open/roll_call states and:
       - Migrate EventSignup rows to the target (skipping conflicts where the
         user already has a signup on the target). Seated rows keep a seat
         while the target has room; the rest join the end of its waitlist,
         which then promotes into any seats still free.
       - Migrate users on the linked future Tournament to the target's
         tournament, except players the move left on the waitlist.
       - Cancel the stale event.
       - Delete the stale event's DiscordEvent row.
       - Delete the stale event's linked Tournament if state == "future".

Run with --apply to commit. Default is dry-run.

Usage:
    python scripts/cleanup_stale_repeater_events.py REPEATER_ID [--apply]

Note: the Discord-side scheduled event living in the guild is NOT removed --
only the local DiscordEvent row. An admin must remove the guild-side event
manually (or extend this script to call the Discord API).
"""

import argparse
import datetime
import os
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.db import transaction  # noqa: E402
from django.db.models import Max  # noqa: E402

from app.cache_utils import invalidate_after_commit  # noqa: E402
from discordbot.models import DiscordEvent  # noqa: E402
from events.capacity import (  # noqa: E402
    has_free_seat,
    lock_event,
    seat_holding_statuses,
)
from events.constants import EventState, SignupAction, SignupStatus  # noqa: E402
from events.ledger import SignupActor, record_signup_change, snapshot  # noqa: E402
from events.line import waitlist_ranks  # noqa: E402
from events.models import (  # noqa: E402
    Event,
    EventRepeater,
    EventSignup,
    SignupLedgerEntry,
)
from events.services import (  # noqa: E402
    _promote_from_waitlist,
    _python_weekday,
    generate_events_for_repeater,
)

STALE_STATES = [EventState.UPCOMING, EventState.SIGNUPS_OPEN]
TARGET_STATES = [EventState.UPCOMING, EventState.SIGNUPS_OPEN, EventState.ROLL_CALL]


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def find_stale_events(repeater: EventRepeater, target_weekday: int) -> list[Event]:
    tz = ZoneInfo(repeater.timezone)
    qs = Event.objects.filter(
        event_repeater=repeater,
        state__in=STALE_STATES,
        scheduled_at__gte=_now_utc(),
    ).order_by("scheduled_at")
    return [
        e
        for e in qs
        if e.scheduled_at.astimezone(tz).date().weekday() != target_weekday
    ]


def find_correct_day_events(
    repeater: EventRepeater, target_weekday: int
) -> list[Event]:
    tz = ZoneInfo(repeater.timezone)
    qs = Event.objects.filter(
        event_repeater=repeater,
        state__in=TARGET_STATES,
        scheduled_at__gte=_now_utc(),
    ).order_by("scheduled_at")
    return [
        e
        for e in qs
        if e.scheduled_at.astimezone(tz).date().weekday() == target_weekday
    ]


def find_target_event(stale: Event, candidates: list[Event]) -> Event | None:
    """Closest candidate by scheduled_at within 7 days, else None."""
    best: Event | None = None
    best_diff = datetime.timedelta(days=7, seconds=1)
    for c in candidates:
        diff = abs(c.scheduled_at - stale.scheduled_at)
        if diff < best_diff:
            best, best_diff = c, diff
    return best


def _move_order(rows: list[EventSignup], stale: Event) -> list[EventSignup]:
    """Seated rows, then the waitlist, then the rest, each in line order."""
    in_line = sorted(rows, key=lambda r: (r.line_seq is None, r.line_seq or 0, r.pk))
    seated = [r for r in in_line if r.status in seat_holding_statuses(stale)]
    waiting = [r for r in in_line if r.status == SignupStatus.WAITLISTED]
    rest = [r for r in in_line if r not in seated and r not in waiting]
    return [*seated, *waiting, *rest]


@transaction.atomic
def migrate_signups(
    stale: Event, target: Event, *, correlation_id: str
) -> tuple[int, int]:
    """Move stale's signups to target. Seated rows keep their seat while target
    has room; the rest join the end of target's waitlist in their stale order."""
    locked = lock_event(target)
    existing = set(
        EventSignup.objects.nocache()
        .filter(event=locked)
        .values_list("user_id", flat=True)
    )
    next_position = (
        EventSignup.objects.nocache()
        .filter(event=locked, status=SignupStatus.WAITLISTED)
        .aggregate(max_pos=Max("waitlist_position"))["max_pos"]
        or 0
    ) + 1
    stale_ranks = waitlist_ranks(stale)
    target_waiting = len(waitlist_ranks(locked))
    moved_ranks: list[int] = []
    actor = SignupActor.system(correlation_id=correlation_id)
    rows = list(
        EventSignup.objects.nocache()
        .filter(event=stale)
        .select_related("user__base_profile")
    )
    moved = 0
    skipped = 0
    first_waitlisted: SignupLedgerEntry | None = None
    for s in _move_order(rows, stale):
        if s.user_id in existing:
            print(f"    skip signup user={s.user_id} ({s.user}) — already on target")
            skipped += 1
            continue
        stale_rank = stale_ranks.get(s.pk)
        if stale_rank is not None:
            moved_ranks.append(stale_rank)
            stale_rank -= sum(1 for gone in moved_ranks if gone < stale_rank)
        before = snapshot(s, extra={"event_id": stale.pk}, waitlist_rank=stale_rank)
        if s.status in seat_holding_statuses(stale) and not has_free_seat(locked):
            s.status = SignupStatus.WAITLISTED
        target_rank: int | None = None
        if s.status == SignupStatus.WAITLISTED:
            s.waitlist_position = next_position
            next_position += 1
            target_waiting += 1
            target_rank = target_waiting
        else:
            s.waitlist_position = None
        s.event = locked
        s.event_team = None
        s.save(
            update_fields=[
                "event",
                "event_team",
                "status",
                "waitlist_position",
                "updated_at",
            ]
        )
        after = snapshot(s, extra={"event_id": target.pk}, waitlist_rank=target_rank)
        source = record_signup_change(
            event=stale,
            subject=s.user,
            actor=actor,
            action=SignupAction.MOVED_EVENT,
            signup=s,
            before=before,
            after=after,
        )
        dest = record_signup_change(
            event=locked,
            subject=s.user,
            actor=actor,
            action=SignupAction.MOVED_EVENT,
            signup=s,
            before=before,
            after=after,
            caused_by=source,
        )
        if s.status == SignupStatus.WAITLISTED and first_waitlisted is None:
            first_waitlisted = dest
        moved += 1
    if first_waitlisted is not None:
        _promote_from_waitlist(locked, cause=first_waitlisted)
    if moved:
        invalidate_after_commit(stale, locked)
    return moved, skipped


def migrate_tournament_users(stale: Event, target: Event) -> int:
    if not (stale.tournament and stale.tournament.state == "future"):
        return 0
    if not (target.tournament and target.tournament.state == "future"):
        return 0
    existing = set(target.tournament.users.values_list("id", flat=True))
    waitlisted = set(
        EventSignup.objects.nocache()
        .filter(event=target, status=SignupStatus.WAITLISTED)
        .values_list("user_id", flat=True)
    )
    moved = 0
    for u in stale.tournament.users.all():
        if u.id in existing or u.id in waitlisted:
            continue
        target.tournament.users.add(u)
        moved += 1
    return moved


def cancel_stale_event(stale: Event) -> None:
    if stale.tournament and stale.tournament.state == "future":
        tournament = stale.tournament
        stale.tournament = None
        stale.save(update_fields=["tournament", "updated_at"])
        tournament.delete()
    DiscordEvent.objects.filter(event=stale).delete()
    stale.transition_state(EventState.CANCELLED)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up stale repeater events.")
    parser.add_argument("repeater_id", type=int)
    parser.add_argument(
        "--apply", action="store_true", help="Commit changes (default: dry-run)"
    )
    args = parser.parse_args()

    try:
        repeater = EventRepeater.objects.get(pk=args.repeater_id)
    except EventRepeater.DoesNotExist:
        print(f"EventRepeater pk={args.repeater_id} not found", file=sys.stderr)
        sys.exit(1)

    if repeater.day_of_week is None:
        print(f"Repeater {repeater.pk} has no day_of_week — nothing to do.")
        return

    target_weekday = _python_weekday(repeater.day_of_week)
    tz = ZoneInfo(repeater.timezone)
    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"=== {mode} — Repeater pk={repeater.pk} {repeater.name!r} ===")
    print(
        f"  frequency={repeater.frequency} day_of_week={repeater.day_of_week} (Sunday=0)"
    )
    print(
        f"  python_weekday={target_weekday}  tz={repeater.timezone}  "
        f"time_of_day={repeater.time_of_day}"
    )
    print(f"  detecting stale states: {[s.value for s in STALE_STATES]}")
    print()

    stale = find_stale_events(repeater, target_weekday)
    print(f"Stale future events: {len(stale)}")
    for e in stale:
        local = e.scheduled_at.astimezone(tz)
        print(
            f"  ev={e.pk} state={e.state} scheduled_at={e.scheduled_at} "
            f"local={local:%a %Y-%m-%d %H:%M} tournament={e.tournament_id}"
        )
    if not stale:
        print("Nothing to clean up.")
        return

    if args.apply:
        with transaction.atomic():
            generated = generate_events_for_repeater(repeater)
        print(f"\nGenerated {len(generated)} new correct-day events.")
        for e in generated:
            print(f"  ev={e.pk} scheduled_at={e.scheduled_at}")
    else:
        print(
            "\n[dry-run] would call generate_events_for_repeater() to create "
            f"correct-day events up to today + {repeater.generate_days_ahead}d"
        )

    candidates = find_correct_day_events(repeater, target_weekday)
    print(f"\nCorrect-day candidates available as targets: {len(candidates)}")
    for c in candidates:
        local = c.scheduled_at.astimezone(tz)
        print(
            f"  ev={c.pk} state={c.state} scheduled_at={c.scheduled_at} "
            f"local={local:%a %Y-%m-%d %H:%M}"
        )

    correlation_id = f"cleanup-{uuid4().hex[:12]}"
    print("\n--- Migration plan ---")
    for stale_ev in stale:
        target = find_target_event(stale_ev, candidates)
        signup_count = EventSignup.objects.filter(event=stale_ev).count()
        tournament_user_count = (
            stale_ev.tournament.users.count() if stale_ev.tournament else 0
        )
        print(
            f"\nev={stale_ev.pk} ({stale_ev.scheduled_at.astimezone(tz):%a %m-%d}) "
            f"signups={signup_count} tournament_users={tournament_user_count}"
        )
        if target:
            print(
                f"  -> target ev={target.pk} ({target.scheduled_at.astimezone(tz):%a %m-%d})"
            )
        else:
            print("  -> NO TARGET WITHIN 7 DAYS — will cancel without migration")

        if not args.apply:
            continue

        with transaction.atomic():
            if target:
                moved, skipped = migrate_signups(
                    stale_ev, target, correlation_id=correlation_id
                )
                t_moved = migrate_tournament_users(stale_ev, target)
                print(
                    f"  migrated signups={moved} skipped_conflicts={skipped} "
                    f"tournament_users={t_moved}"
                )
            cancel_stale_event(stale_ev)
            print(f"  cancelled ev={stale_ev.pk}")

    print()
    if not args.apply:
        print("DRY RUN — no changes made. Re-run with --apply to commit.")
    else:
        print(
            "Done. NOTE: any Discord-side scheduled events created by the stale "
            "events still exist in the guild — clean them up manually."
        )


if __name__ == "__main__":
    main()
