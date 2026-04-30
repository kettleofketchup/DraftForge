# Event reminder scheduling registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc reminder polling with a declarative `ScheduledReminder` registry, eliminate dead reminder fields, prevent polling-overlap double-fires via a DB unique constraint, and fix series-edit bugs that cause duplicate occurrences and "wrong day" reminder firings.

**Architecture:** A `scheduling/registry.py` module declares all reminder types as data; `scheduling/fire.py` iterates the registry on each 30-second beat poll. Once-fired-sticky semantics — `DiscordMessageLog` rows gate re-fires permanently. A Postgres partial unique index on `DiscordMessageLog(source, source_id) WHERE success = TRUE` prevents concurrent-poll double-fires. `sync_future_events` cascades reminder fields generically (union of `REMINDERS` field names) and calls `invalidate_after_commit` per row to keep cacheops in sync. The announcement reminder, currently inert, is wired through the registry.

**Tech Stack:** Django 5, Django REST Framework, Celery 5, django-cacheops (Redis), Daphne (Channels), React 19 + TypeScript, Zod, TanStack Query, Playwright. Backend tests via `just test::run`, frontend tests via `just test::pw::spec`.

**Spec:** `docs/superpowers/specs/2026-04-30-event-reminder-scheduling-registry-design.md` (decisions Q1–Q13 are normative)

**Three-phase rollout:**

- **Phase 0 (PR-0)** — frontend Zod loosen. One file. Ships first, sits one release cycle.
- **Phase 1 (PR-1)** — registry + dead-field cleanup + idempotency guard. Backend-heavy. Ships after PR-0 has cycled.
- **Phase 2 (PR-2)** — series row-level fixes + frontend cleanup. Ships after PR-1.

Each phase produces deployable, testable software on its own.

---

## Phase 0 — Frontend Zod loosen (PR-0)

### Task 0.1: Make `discord_subscriber_dm*` Zod fields optional

**Files:**
- Modify: `frontend/app/components/events/schemas.ts` (lines ~84-85, ~260-261)
- Test: `frontend/tests/playwright/e2e/16-events/05-event-form-validation.spec.ts` (find or create)

**Why:** PR-1 will drop `discord_subscriber_dm` and `discord_subscriber_dm_hours` from backend Event/EventRepeater. Until both releases ship, frontend bundles must tolerate either presence or absence of the keys without failing Zod parse.

- [ ] **Step 1: Read current schema definitions**

```bash
grep -n "discord_subscriber_dm" frontend/app/components/events/schemas.ts
```

Expected: 4 lines — required boolean and integer at two locations (eventSchema and discordConfigSchema).

- [ ] **Step 2: Write the failing parse test**

Create `frontend/tests/unit/event-schema-tolerance.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { eventSchema, discordConfigSchema } from '@/components/events/schemas'

describe('discord_subscriber_dm tolerance', () => {
  it('eventSchema parses payload missing discord_subscriber_dm fields', () => {
    const payloadWithoutSubscriberDm = {
      // build a valid event payload but omit discord_subscriber_dm and discord_subscriber_dm_hours
      // copy the minimal valid shape from existing tests, drop the two fields
    }
    expect(() => eventSchema.parse(payloadWithoutSubscriberDm)).not.toThrow()
  })

  it('discordConfigSchema parses payload missing discord_subscriber_dm fields', () => {
    const payloadWithoutSubscriberDm = {
      discord_announcement: false,
      discord_announcement_channel_id: null,
      discord_announcement_hours: 24,
      discord_signup_reminder: false,
      discord_signup_reminder_hours: 24,
      discord_confirm_attendance: false,
      discord_confirm_attendance_hours: 2,
      discord_profile_reminder: false,
      discord_profile_reminder_hours: 24,
      discord_post_signups: false,
      discord_notify_new_events: false,
    }
    expect(() => discordConfigSchema.parse(payloadWithoutSubscriberDm)).not.toThrow()
  })
})
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
cd frontend && npx vitest run tests/unit/event-schema-tolerance.test.ts
```

Expected: FAIL with `discord_subscriber_dm: Required` and `discord_subscriber_dm_hours: Required`.

- [ ] **Step 4: Loosen the schema**

Edit `frontend/app/components/events/schemas.ts`. At lines ~84-85 (eventSchema):

```typescript
// before
discord_subscriber_dm: z.boolean(),
discord_subscriber_dm_hours: z.number().int().min(1),

// after
discord_subscriber_dm: z.boolean().optional(),
discord_subscriber_dm_hours: z.number().int().min(1).optional(),
```

Same change at lines ~260-261 (discordConfigSchema).

- [ ] **Step 5: Run the test — confirm it passes**

```bash
cd frontend && npx vitest run tests/unit/event-schema-tolerance.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run the full Playwright event-form suite to catch regressions**

```bash
just test::pw::spec event-form
```

Expected: all existing tests pass — making fields optional is strictly more permissive.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/events/schemas.ts frontend/tests/unit/event-schema-tolerance.test.ts
git commit -m "feat(events): tolerate missing discord_subscriber_dm fields in Zod

Prep for PR-1 backend column drop. Schemas now accept payloads with or
without these keys, enabling a one-release deploy gap."
```

---

## Phase 1 — Registry, dead-field cleanup, idempotency guard (PR-1)

### Task 1.1: Add `EventSlimSerializer` reminder fields

**Files:**
- Modify: `backend/events/serializers.py:166-185` (EventSlimSerializer Meta.fields)
- Test: `backend/events/tests/test_serializers.py` (add or extend)

**Why:** `EventSlimSerializer` is what `get_events_list` returns to the celery worker. The fire path calls `getattr(ev, reminder.hours_field)` against the deserialized result. Without these fields exposed, the fire path will always read None/defaults. This is a prerequisite for everything downstream.

- [ ] **Step 1: Write the failing serializer-coverage test**

Create or extend `backend/events/tests/test_serializers.py`:

```python
from django.test import TestCase
from events.serializers import EventSlimSerializer
from events.models import Event

REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH = [
    "discord_announcement",
    "discord_announcement_hours",
    "discord_signup_reminder",
    "discord_signup_reminder_hours",
    "discord_confirm_attendance",
    "discord_confirm_attendance_hours",
    "discord_profile_reminder",
    "discord_profile_reminder_hours",
    "discord_announcement_channel_id",
]

class EventSlimSerializerReminderFieldsTest(TestCase):
    def test_slim_serializer_exposes_all_reminder_fields(self):
        exposed = set(EventSlimSerializer.Meta.fields)
        missing = [f for f in REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH if f not in exposed]
        self.assertEqual(missing, [], f"EventSlimSerializer missing: {missing}")
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_serializers.EventSlimSerializerReminderFieldsTest -v 2'
```

Expected: FAIL — list of missing fields.

- [ ] **Step 3: Add the fields to the serializer**

Edit `backend/events/serializers.py:166-185`. Append to the `fields` list:

```python
fields = [
    "id",
    "organization",
    "organization_name",
    "name",
    "scheduled_at",
    "state",
    "game_type",
    "tournament_name",
    "tournament_league",
    "tournament_type",
    "draft_type",
    "people_per_team",
    "number_of_teams",
    "signup_count",
    "confirmed_count",
    "event_repeater",
    # Reminder fields needed by fire_due_reminders
    "discord_announcement",
    "discord_announcement_hours",
    "discord_announcement_channel_id",
    "discord_signup_reminder",
    "discord_signup_reminder_hours",
    "discord_confirm_attendance",
    "discord_confirm_attendance_hours",
    "discord_profile_reminder",
    "discord_profile_reminder_hours",
]
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_serializers.EventSlimSerializerReminderFieldsTest -v 2'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/serializers.py backend/events/tests/test_serializers.py
git commit -m "feat(events): expose reminder fields on EventSlimSerializer

The fire path reads these fields off slim payloads from get_events_list.
Test asserts every fire-path field is present so additions stay in sync."
```

### Task 1.2: Add Postgres partial unique index migration

**Files:**
- Create: `backend/events/migrations/0XXX_discord_message_log_unique_success.py` (auto-numbered by makemigrations; verify column name first)
- Test: `backend/events/tests/test_idempotency.py` (new file)

**Why:** Two concurrent polls can each see `check_message_log_exists=False` and both dispatch a reminder task. The unique index forces the second `DiscordMessageLog.objects.create(...)` to raise `IntegrityError`, giving us a fail-loud idempotency primitive.

- [ ] **Step 1: Verify the success-flag column name**

```bash
grep -n "success\|delivered\|succeeded" backend/discordbot/models.py | head -20
```

Expected: locate `DiscordMessageLog` model. Note the boolean field name (most likely `success`). Substitute it below if different.

- [ ] **Step 2: Write the failing concurrency test**

Create `backend/events/tests/test_idempotency.py`:

```python
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from discordbot.models import DiscordMessageLog


class DiscordMessageLogUniquenessTest(TransactionTestCase):
    def test_two_successful_logs_for_same_source_event_collide(self):
        DiscordMessageLog.objects.create(
            source="signup_reminder",
            source_id=1,
            success=True,
            message_id="abc",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DiscordMessageLog.objects.create(
                    source="signup_reminder",
                    source_id=1,
                    success=True,
                    message_id="def",
                )

    def test_failed_log_does_not_collide_with_successful(self):
        DiscordMessageLog.objects.create(
            source="signup_reminder",
            source_id=2,
            success=True,
        )
        # A failed attempt should not violate the partial index
        DiscordMessageLog.objects.create(
            source="signup_reminder",
            source_id=2,
            success=False,
        )

    def test_different_source_or_event_does_not_collide(self):
        DiscordMessageLog.objects.create(
            source="signup_reminder", source_id=3, success=True
        )
        DiscordMessageLog.objects.create(
            source="signup_reminder", source_id=4, success=True
        )
        DiscordMessageLog.objects.create(
            source="attendance_reminder", source_id=3, success=True
        )
```

- [ ] **Step 3: Run the test — confirm it fails (no constraint yet)**

```bash
just test::run 'python manage.py test events.tests.test_idempotency -v 2'
```

Expected: FAIL — `test_two_successful_logs_for_same_source_event_collide` does NOT raise IntegrityError because no constraint exists.

- [ ] **Step 4: Create the migration**

```bash
just dev::exec backend python manage.py makemigrations discordbot --empty --name discord_message_log_unique_success
```

Expected: migration file created.

Edit the new migration file to add the partial unique index:

```python
from django.contrib.postgres.indexes import OpClass
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "<previous_migration_name>"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="discordmessagelog",
            constraint=models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=models.Q(success=True),
                name="uniq_discord_message_log_source_event_when_success",
            ),
        ),
    ]
```

Note: replace `<previous_migration_name>` with the actual name shown in the new migration's `dependencies`.

- [ ] **Step 5: Apply the migration**

```bash
just db::migrate::all
```

Expected: migration applied across dev/test/prod DBs.

- [ ] **Step 6: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_idempotency -v 2'
```

Expected: all 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/discordbot/migrations/ backend/events/tests/test_idempotency.py
git commit -m "feat(discord): partial unique index on DiscordMessageLog

Postgres partial unique index on (source, source_id) WHERE success=TRUE.
Provides a DB-level idempotency guard so concurrent celery polls cannot
produce duplicate successful reminder rows. Failed/pending rows can
coexist freely."
```

### Task 1.3: Wrap reminder tasks in IntegrityError-safe transactions

**Files:**
- Modify: `backend/events/tasks.py` — `send_event_announcement` (line ~192), `send_subscriber_notifications` (line ~858)
- Test: `backend/events/tests/test_idempotency.py` (extend)

**Why:** Tasks must catch `IntegrityError` from the unique constraint as a clean "lost the race; another worker won" path. Without this, the second worker logs a traceback as a task failure.

- [ ] **Step 1: Write the failing race-handling test**

Append to `backend/events/tests/test_idempotency.py`:

```python
from unittest.mock import patch
from events.tasks import send_event_announcement
from events.tests.factories import EventFactory  # or whatever the project uses


class ReminderTaskRaceTest(TransactionTestCase):
    def test_send_event_announcement_swallows_integrity_error(self):
        event = EventFactory(discord_announcement=True, discord_announcement_channel_id="123")
        # Pre-create the success log row to simulate "another worker already won"
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=event.pk,
            success=True,
            message_id="prior",
        )
        # The task should complete cleanly, not raise
        result = send_event_announcement(event.pk)
        self.assertIn("already", result.lower())  # or whatever the success-but-noop string is
        # No additional success row was written
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="event_announcement", source_id=event.pk, success=True
            ).count(),
            1,
        )
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_idempotency.ReminderTaskRaceTest -v 2'
```

Expected: FAIL with `IntegrityError` traceback.

- [ ] **Step 3: Wrap `send_event_announcement` in atomic + IntegrityError catch**

Edit `backend/events/tasks.py:192` (the `send_event_announcement` function). Wrap the body of the task that creates the `DiscordMessageLog` row:

```python
from django.db import IntegrityError, transaction

@shared_task
def send_event_announcement(event_id):
    """..."""
    # ... existing setup code that loads event, builds embed, etc ...

    try:
        with transaction.atomic():
            response = sync_send_embed_with_components(
                channel_id=event.discord_announcement_channel_id,
                embed=result["embed"],
                components=result.get("components"),
                source="event_announcement",
                source_id=event.pk,
            )
            # The DiscordMessageLog row is created inside sync_send_embed_with_components.
            # If a competing worker already inserted a success row, the unique constraint
            # raises IntegrityError here.
    except IntegrityError:
        return f"Event {event_id} announcement already logged by another worker — skipping"

    return f"Sent announcement for event {event_id}"
```

Apply the same pattern to `send_subscriber_notifications` (line ~858) for the `signup_reminder` source.

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_idempotency.ReminderTaskRaceTest -v 2'
```

Expected: PASS.

- [ ] **Step 5: Run the full reminder-task suite to catch regressions**

```bash
just test::run 'python manage.py test events.tests.test_discord_tasks events.tests.test_discord_integration -v 2'
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/events/tasks.py backend/events/tests/test_idempotency.py
git commit -m "feat(events): IntegrityError-safe reminder task sends

Wrap send_event_announcement and send_subscriber_notifications in
@transaction.atomic. Catch IntegrityError from the partial unique index
as a clean lost-the-race exit path."
```

### Task 1.4: Extract `attendance_reminder` into a top-level shared task

**Files:**
- Modify: `backend/events/tasks.py:795-823` — currently inline in `check_event_reminders`
- Test: `backend/events/tests/test_attendance_reminder_task.py` (new)

**Why:** The inline branch in `check_event_reminders` does a synchronous Discord HTTP call inside the polling task — the very thing that creates the >30s overlap window. Extracting to a `.delay()`-able task aligns with how the other reminders work and lets the registry dispatch it generically.

- [ ] **Step 1: Read the existing inline code**

```bash
sed -n '795,825p' backend/events/tasks.py
```

Note the embed-building, send call, and log structure.

- [ ] **Step 2: Write the failing test for the extracted task**

Create `backend/events/tests/test_attendance_reminder_task.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from events.tasks import send_attendance_reminder
from events.tests.factories import EventFactory


class SendAttendanceReminderTest(TestCase):
    @patch("events.tasks.sync_send_embed_with_components")
    def test_sends_attendance_embed_to_announcement_channel(self, mock_send):
        mock_send.return_value = {"id": "msg_1"}
        event = EventFactory(
            discord_confirm_attendance=True,
            discord_announcement_channel_id="ch_123",
            state="signups_open",
        )
        result = send_attendance_reminder(event.pk)
        mock_send.assert_called_once()
        self.assertIn("ch_123", str(mock_send.call_args))
        self.assertIn(str(event.pk), result)

    @patch("events.tasks.sync_send_embed_with_components")
    def test_skips_if_no_announcement_channel(self, mock_send):
        event = EventFactory(
            discord_confirm_attendance=True,
            discord_announcement_channel_id=None,
        )
        result = send_attendance_reminder(event.pk)
        mock_send.assert_not_called()
        self.assertIn("no channel", result.lower())
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_attendance_reminder_task -v 2'
```

Expected: FAIL with `ImportError: cannot import name 'send_attendance_reminder'`.

- [ ] **Step 4: Add the new shared task**

Insert into `backend/events/tasks.py` (a sensible location is just after `send_event_announcement`):

```python
@shared_task
def send_attendance_reminder(event_id):
    """Post the attendance-confirmation embed to the announcement channel.

    Extracted from the inline block formerly in check_event_reminders.
    Idempotency is guaranteed by the partial unique index on
    DiscordMessageLog(source='attendance_reminder', source_id=event_id, success=True).
    """
    from app.internal_client import get_event_for_task
    from discordbot.utils import sync_send_embed_with_components
    from events.discord import build_attendance_reminder_embed
    from django.db import IntegrityError, transaction

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"

    result = build_attendance_reminder_embed(event)
    try:
        with transaction.atomic():
            sync_send_embed_with_components(
                channel_id=event.discord_announcement_channel_id,
                embed=result["embed"],
                components=result.get("components"),
                source="attendance_reminder",
                source_id=event.pk,
            )
    except IntegrityError:
        return f"Attendance reminder for event {event_id} already logged"

    return f"Sent attendance reminder for event {event_id}"
```

- [ ] **Step 5: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_attendance_reminder_task -v 2'
```

Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add backend/events/tasks.py backend/events/tests/test_attendance_reminder_task.py
git commit -m "feat(events): extract send_attendance_reminder as top-level task

Pulls the inline block out of check_event_reminders and gives it the
same IntegrityError-safe shape as the other reminder tasks. Inline
caller removed in a later task."
```

### Task 1.5: Extract `profile_reminder` into a top-level shared task

**Files:**
- Modify: `backend/events/tasks.py:826-853` — inline in `check_event_reminders`
- Test: `backend/events/tests/test_profile_reminder_task.py` (new)

**Why:** Same reasoning as Task 1.4 — the inline block must become a `.delay()`-able task before the registry can dispatch it.

- [ ] **Step 1: Write the failing test**

Create `backend/events/tests/test_profile_reminder_task.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from events.tasks import send_profile_reminder
from events.tests.factories import EventFactory


class SendProfileReminderTest(TestCase):
    @patch("events.tasks.sync_send_embed_with_components")
    def test_sends_profile_embed_to_announcement_channel(self, mock_send):
        mock_send.return_value = {"id": "msg_1"}
        event = EventFactory(
            discord_profile_reminder=True,
            discord_announcement_channel_id="ch_123",
            state="signups_open",
        )
        result = send_profile_reminder(event.pk)
        mock_send.assert_called_once()
        self.assertIn(str(event.pk), result)

    @patch("events.tasks.sync_send_embed_with_components")
    def test_skips_if_no_announcement_channel(self, mock_send):
        event = EventFactory(
            discord_profile_reminder=True,
            discord_announcement_channel_id=None,
        )
        result = send_profile_reminder(event.pk)
        mock_send.assert_not_called()
        self.assertIn("no channel", result.lower())
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_profile_reminder_task -v 2'
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add the task to `tasks.py`**

Insert next to `send_attendance_reminder`:

```python
@shared_task
def send_profile_reminder(event_id):
    """Post the profile-completion reminder embed to the announcement channel.

    Extracted from the inline block formerly in check_event_reminders.
    """
    from app.internal_client import get_event_for_task
    from discordbot.utils import sync_send_embed_with_components
    from events.discord import build_profile_reminder_embed
    from django.db import IntegrityError, transaction

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"

    result = build_profile_reminder_embed(event)
    try:
        with transaction.atomic():
            sync_send_embed_with_components(
                channel_id=event.discord_announcement_channel_id,
                embed=result["embed"],
                components=result.get("components"),
                source="profile_reminder",
                source_id=event.pk,
            )
    except IntegrityError:
        return f"Profile reminder for event {event_id} already logged"

    return f"Sent profile reminder for event {event_id}"
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_profile_reminder_task -v 2'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/tasks.py backend/events/tests/test_profile_reminder_task.py
git commit -m "feat(events): extract send_profile_reminder as top-level task"
```

### Task 1.6: Create `events/scheduling/registry.py`

**Files:**
- Create: `backend/events/scheduling/__init__.py` (empty)
- Create: `backend/events/scheduling/registry.py`
- Test: `backend/events/tests/test_scheduling_registry.py` (new)

**Why:** Single source of truth for reminder declarations. The dataclass shape and the import-time validator are the two foundations the rest of the phase builds on.

- [ ] **Step 1: Write the failing CI guardrail tests**

Create `backend/events/tests/test_scheduling_registry.py`:

```python
import re
from celery import current_app
from django.test import TestCase

from events.models import Event, EventRepeater
from events.scheduling.registry import REMINDERS, ScheduledReminder
from events.serializers import EventSlimSerializer


HOURS_FIELD_RE = re.compile(r"^discord_.*_hours$")


class RegistryGuardrailsTest(TestCase):
    def test_every_discord_hours_field_is_in_registry(self):
        """Every discord_*_hours field on Event/EventRepeater must be registered."""
        registered = {r.hours_field for r in REMINDERS}
        # Exception list — fields known to be deprecated/dropped
        # (must be empty post-PR-1)
        deprecated = set()

        for model in (Event, EventRepeater):
            model_fields = {
                f.name for f in model._meta.get_fields()
                if hasattr(f, "name") and HOURS_FIELD_RE.match(f.name)
            }
            missing = model_fields - registered - deprecated
            self.assertEqual(
                missing, set(),
                f"{model.__name__} has unregistered _hours fields: {missing}",
            )

    def test_every_enabled_field_resolves(self):
        """Every reminder.enabled_field must be a real boolean on Event."""
        event_fields = {f.name for f in Event._meta.get_fields()}
        for r in REMINDERS:
            self.assertIn(
                r.enabled_field, event_fields,
                f"Reminder {r.key!r} enabled_field {r.enabled_field!r} not on Event",
            )

    def test_every_hours_field_resolves(self):
        event_fields = {f.name for f in Event._meta.get_fields()}
        for r in REMINDERS:
            self.assertIn(
                r.hours_field, event_fields,
                f"Reminder {r.key!r} hours_field {r.hours_field!r} not on Event",
            )

    def test_every_hours_field_in_slim_serializer(self):
        """The fire path reads slim payloads; every hours/enabled field
        must be exposed."""
        exposed = set(EventSlimSerializer.Meta.fields)
        for r in REMINDERS:
            self.assertIn(
                r.hours_field, exposed,
                f"EventSlimSerializer missing {r.hours_field!r} for {r.key!r}",
            )
            self.assertIn(
                r.enabled_field, exposed,
                f"EventSlimSerializer missing {r.enabled_field!r} for {r.key!r}",
            )

    def test_every_task_name_is_registered_with_celery(self):
        """Every reminder.task_name must resolve via current_app.tasks.get."""
        for r in REMINDERS:
            task = current_app.tasks.get(r.task_name)
            self.assertIsNotNone(
                task,
                f"Reminder {r.key!r} task_name {r.task_name!r} is not a registered "
                f"celery task. Check the @shared_task decorator and module path.",
            )

    def test_keys_are_unique(self):
        keys = [r.key for r in REMINDERS]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate reminder keys")

    def test_log_sources_are_unique(self):
        sources = [r.log_source for r in REMINDERS]
        self.assertEqual(len(sources), len(set(sources)), "Duplicate log_source values")
```

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
just test::run 'python manage.py test events.tests.test_scheduling_registry -v 2'
```

Expected: FAIL with `ImportError: cannot import name 'REMINDERS'`.

- [ ] **Step 3: Create the empty package init**

Create `backend/events/scheduling/__init__.py`:

```python
"""Declarative reminder registry. See registry.py for the REMINDERS list."""
```

- [ ] **Step 4: Create the registry module**

Create `backend/events/scheduling/registry.py`:

```python
"""Declarative reminder registry — single source of truth.

Adding a new reminder = one entry in REMINDERS plus the corresponding
@shared_task. The CI test suite (test_scheduling_registry.py) verifies
field coverage, task registration, and slim-serializer exposure.
"""

from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class ScheduledReminder:
    key: str
    task_name: str  # "events.tasks.send_event_announcement"
    hours_field: str
    enabled_field: str
    required_states: FrozenSet[str]
    log_source: str
    requires_repeater: bool = False


REMINDERS: list[ScheduledReminder] = [
    ScheduledReminder(
        key="announcement",
        task_name="events.tasks.send_event_announcement",
        hours_field="discord_announcement_hours",
        enabled_field="discord_announcement",
        required_states=frozenset({"upcoming", "signups_open"}),
        log_source="event_announcement",
    ),
    ScheduledReminder(
        key="signup_reminder",
        task_name="events.tasks.send_subscriber_notifications",
        hours_field="discord_signup_reminder_hours",
        enabled_field="discord_signup_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="signup_reminder",
        requires_repeater=True,
    ),
    ScheduledReminder(
        key="attendance_reminder",
        task_name="events.tasks.send_attendance_reminder",
        hours_field="discord_confirm_attendance_hours",
        enabled_field="discord_confirm_attendance",
        required_states=frozenset({"signups_open", "roll_call"}),
        log_source="attendance_reminder",
    ),
    ScheduledReminder(
        key="profile_reminder",
        task_name="events.tasks.send_profile_reminder",
        hours_field="discord_profile_reminder_hours",
        enabled_field="discord_profile_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="profile_reminder",
    ),
]


def reminder_field_union() -> set[str]:
    """All hours/enabled fields used by any reminder. Used by sync_future_events
    to cascade reminder fields onto upcoming Event rows generically."""
    return {r.hours_field for r in REMINDERS} | {r.enabled_field for r in REMINDERS}
```

- [ ] **Step 5: Run the tests — confirm they pass**

```bash
just test::run 'python manage.py test events.tests.test_scheduling_registry -v 2'
```

Expected: PASS (all 7 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/events/scheduling/ backend/events/tests/test_scheduling_registry.py
git commit -m "feat(events): declarative ScheduledReminder registry

Single source of truth for reminder definitions. CI guardrails enforce:
- every discord_*_hours model field is registered
- every enabled_field/hours_field resolves to a real Event field
- every hours_field and enabled_field is exposed by EventSlimSerializer
- every task_name resolves via current_app.tasks.get at import time
- keys and log_sources are unique"
```

### Task 1.7: Create `events/scheduling/fire.py`

**Files:**
- Create: `backend/events/scheduling/fire.py`
- Test: `backend/events/tests/test_fire_due_reminders.py` (new)

**Why:** The fire path is the runtime consumer of the registry. Replaces the body of `check_event_reminders`.

- [ ] **Step 1: Write the failing fire-path test**

Create `backend/events/tests/test_fire_due_reminders.py`:

```python
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog
from events.scheduling.fire import fire_due_reminders
from events.tests.factories import EventFactory, EventRepeaterFactory


class FireDueRemindersTest(TestCase):
    @patch("events.scheduling.fire.current_app.send_task")
    def test_fires_announcement_when_threshold_passed(self, mock_send):
        repeater = EventRepeaterFactory()
        event = EventFactory(
            event_repeater=repeater,
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
            discord_announcement_hours=24,
            scheduled_at=timezone.now() + timedelta(hours=12),  # threshold = -12h ago
            state="upcoming",
        )
        fire_due_reminders()
        mock_send.assert_any_call(
            "events.tasks.send_event_announcement", args=[event.pk]
        )

    @patch("events.scheduling.fire.current_app.send_task")
    def test_does_not_fire_before_threshold(self, mock_send):
        repeater = EventRepeaterFactory()
        EventFactory(
            event_repeater=repeater,
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
            discord_announcement_hours=24,
            scheduled_at=timezone.now() + timedelta(days=7),  # threshold = +6 days
            state="upcoming",
        )
        fire_due_reminders()
        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_skips_if_already_fired(self, mock_send):
        event = EventFactory(
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
            discord_announcement_hours=24,
            scheduled_at=timezone.now() + timedelta(hours=12),
            state="upcoming",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement", source_id=event.pk, success=True,
        )
        fire_due_reminders()
        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_skips_if_disabled(self, mock_send):
        EventFactory(
            discord_announcement=False,
            discord_announcement_hours=24,
            scheduled_at=timezone.now() + timedelta(hours=12),
            state="upcoming",
        )
        fire_due_reminders()
        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_signup_reminder_requires_repeater(self, mock_send):
        # Single event with signup reminder enabled — should NOT fire
        EventFactory(
            event_repeater=None,
            discord_signup_reminder=True,
            discord_signup_reminder_hours=24,
            scheduled_at=timezone.now() + timedelta(hours=12),
            state="signups_open",
        )
        fire_due_reminders()
        signup_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_subscriber_notifications"
        ]
        self.assertEqual(signup_calls, [])
```

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
just test::run 'python manage.py test events.tests.test_fire_due_reminders -v 2'
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create the fire module**

Create `backend/events/scheduling/fire.py`:

```python
"""Fire path — replaces the body of check_event_reminders.

Iterates the REMINDERS registry every 30 seconds. For each candidate
event in the right state, evaluates `now >= scheduled_at - hours` and
dispatches the reminder task by name via celery's app registry.

Idempotency: in-process check via DiscordMessageLog is an optimization;
the actual guarantee is the partial unique index on
DiscordMessageLog(source, source_id) WHERE success=TRUE.
"""

from datetime import timedelta
from celery import current_app
from django.utils import timezone

from events.scheduling.registry import REMINDERS, ScheduledReminder


def fire_due_reminders():
    """Walk REMINDERS, dispatching tasks for each due-and-unfired reminder."""
    from app.internal_client import (
        check_message_log_exists,
        get_events_list,
    )

    now = timezone.now()

    for reminder in REMINDERS:
        candidates = _candidates_for(reminder, get_events_list)
        for ev in candidates:
            if not _ev_attr(ev, reminder.enabled_field):
                continue
            if check_message_log_exists(reminder.log_source, _ev_attr(ev, "id")):
                continue  # once-fired-stays-fired

            hours = _ev_attr(ev, reminder.hours_field) or 0
            if hours <= 0:
                continue

            scheduled_at = _parse_scheduled_at(_ev_attr(ev, "scheduled_at"))
            threshold = scheduled_at - timedelta(hours=hours)
            if now >= threshold:
                current_app.send_task(reminder.task_name, args=[_ev_attr(ev, "id")])

    return f"Checked {len(REMINDERS)} reminder types"


def _candidates_for(reminder: ScheduledReminder, get_events_list):
    """Build the get_events_list filter from the reminder's required_states
    and requires_repeater."""
    states_csv = ",".join(sorted(reminder.required_states))
    kwargs = {"states": states_csv}
    if reminder.requires_repeater:
        kwargs["has_repeater"] = "true"
    return get_events_list(**kwargs)


def _ev_attr(ev, name):
    """Read an attribute off the event payload from get_events_list.
    The internal client returns dict-likes; support both dict and object access."""
    if isinstance(ev, dict):
        return ev.get(name)
    return getattr(ev, name, None)


def _parse_scheduled_at(value):
    """get_events_list returns ISO strings for datetimes; parse to aware datetime."""
    if isinstance(value, str):
        from dateutil.parser import isoparse
        return isoparse(value)
    return value
```

- [ ] **Step 4: Run the tests — confirm they pass**

```bash
just test::run 'python manage.py test events.tests.test_fire_due_reminders -v 2'
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/events/scheduling/fire.py backend/events/tests/test_fire_due_reminders.py
git commit -m "feat(events): fire_due_reminders walks the REMINDERS registry

Replaces the inline branches in check_event_reminders. Dispatches by
celery task name (string) via current_app.send_task — task: Callable
in the dataclass would risk circular imports."
```

### Task 1.8: Replace `check_event_reminders` body and add worker safety

**Files:**
- Modify: `backend/events/tasks.py:738-855`
- Test: `backend/events/tests/test_check_event_reminders_delegate.py` (new)

**Why:** The polling task name and beat schedule must stay the same. Only its body changes — to a one-line call into `fire_due_reminders`. `task_acks_late` and `task_reject_on_worker_lost` ensure a crashed worker requeues the poll instead of dropping it.

- [ ] **Step 1: Write the failing delegation test**

Create `backend/events/tests/test_check_event_reminders_delegate.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from events.tasks import check_event_reminders


class CheckEventRemindersDelegateTest(TestCase):
    @patch("events.tasks.fire_due_reminders")
    def test_delegates_to_fire_due_reminders(self, mock_fire):
        mock_fire.return_value = "ok"
        check_event_reminders()
        mock_fire.assert_called_once()

    def test_task_has_acks_late_and_reject_on_worker_lost(self):
        # Celery exposes options on the task instance
        self.assertTrue(check_event_reminders.acks_late)
        self.assertTrue(check_event_reminders.reject_on_worker_lost)
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_check_event_reminders_delegate -v 2'
```

Expected: FAIL — current implementation does not delegate, and lacks acks_late.

- [ ] **Step 3: Replace the body of `check_event_reminders`**

In `backend/events/tasks.py`, replace lines 738-855 with:

```python
@shared_task(acks_late=True, reject_on_worker_lost=True)
def check_event_reminders():
    """Beat-scheduled every 30s. Delegates to the registry-driven fire path.

    Note (2026-04-30): DiscordMessageLog IS cached by cacheops (60-min TTL,
    invalidated on insert). The unique partial index on (source, source_id)
    WHERE success=TRUE is the actual idempotency primitive — concurrent
    polls would race past the in-process exists() check, but the DB
    constraint serializes the writes.
    """
    from events.scheduling.fire import fire_due_reminders
    return fire_due_reminders()
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_check_event_reminders_delegate -v 2'
```

Expected: PASS.

- [ ] **Step 5: Run the broader event-task suite to catch regressions**

```bash
just test::run 'python manage.py test events.tests -v 2'
```

Expected: all tests pass except any that explicitly test the removed inline behavior — those should be updated or removed alongside.

- [ ] **Step 6: Commit**

```bash
git add backend/events/tasks.py backend/events/tests/test_check_event_reminders_delegate.py
git commit -m "feat(events): check_event_reminders delegates to fire_due_reminders

Body becomes a one-line call to fire_due_reminders(). Adds
acks_late=True + reject_on_worker_lost=True so a crashed worker requeues
the poll instead of dropping it. Stale comment about DiscordMessageLog
caching is corrected."
```

### Task 1.9: Remove immediate `notify_event_announced` dispatch

**Files:**
- Modify: `backend/events/views.py` (lines ~376, ~420, ~551)
- Modify: `backend/events/services.py` (line ~651)
- Test: `backend/events/tests/test_announcement_scheduled.py` (new)

**Why:** With the announcement now in `REMINDERS`, the immediate `.delay()` dispatch on save would race the scheduled fire and create a guaranteed duplicate (or, worse, supersede the scheduled fire by writing the log row first). Remove all four call sites.

- [ ] **Step 1: Write the failing scheduled-not-immediate test**

Create `backend/events/tests/test_announcement_scheduled.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from events.tests.factories import EventFactory


class AnnouncementScheduledNotImmediateTest(TestCase):
    @patch("events.tasks.send_event_announcement.delay")
    def test_event_create_does_not_immediately_dispatch_announcement(self, mock_delay):
        EventFactory(
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
        )
        mock_delay.assert_not_called()

    @patch("events.tasks.send_event_announcement.delay")
    def test_event_update_does_not_immediately_dispatch_announcement(self, mock_delay):
        event = EventFactory(
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
        )
        event.name = "Edited"
        event.save()
        mock_delay.assert_not_called()
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_announcement_scheduled -v 2'
```

Expected: FAIL (the immediate dispatch still happens).

- [ ] **Step 3: Remove call sites in views.py**

Edit `backend/events/views.py`. At the three locations (~376, ~420, ~551), remove the line:

```python
notify_event_announced(event)
```

Also remove the `from events.discord.dispatch import notify_event_announced` import if it has no remaining uses in the file.

- [ ] **Step 4: Remove call site in services.py**

Edit `backend/events/services.py:651` (in `generate_events_for_repeater`):

```python
# remove this block (~3 lines):
if event.discord_announcement and event.discord_announcement_channel_id:
    notify_event_announced(event)
```

- [ ] **Step 5: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_announcement_scheduled -v 2'
```

Expected: PASS.

- [ ] **Step 6: Run broader tests to catch regressions**

```bash
just test::run 'python manage.py test events.tests -v 2'
```

Expected: all tests pass. Some existing tests may have been asserting immediate dispatch — update them to assert the scheduled fire path is reached instead, or remove them if covered by `test_fire_due_reminders.py`.

- [ ] **Step 7: Commit**

```bash
git add backend/events/views.py backend/events/services.py backend/events/tests/test_announcement_scheduled.py
git commit -m "feat(events): announcement is now scheduled, not immediate

Removes notify_event_announced dispatch from EventViewSet.perform_update
(3 call sites) and generate_events_for_repeater. The registry's scheduled
fire path is the sole producer of event_announcement messages.

Behavioral change: announcements no longer post seconds after save —
they post discord_announcement_hours before scheduled_at (default 24h)."
```

### Task 1.10: Generic cascade in `sync_future_events` + cacheops invalidation

**Files:**
- Modify: `backend/events/services.py:662-691`
- Modify: `backend/events/views.py:190-195` (EventRepeaterViewSet.perform_update)
- Test: `backend/events/tests/test_sync_future_events_cascade.py` (new)

**Why:** Currently `sync_future_events` cascades a hand-coded list of fields. Replacing this with the union of `REMINDERS` field names means future reminder additions cascade automatically. The `invalidate_after_commit` calls close the cacheops staleness gap that otherwise delays edited values reaching the fire path.

- [ ] **Step 1: Read the current cascade**

```bash
sed -n '662,695p' backend/events/services.py
```

Note the current `update_fields` list in the per-row save.

- [ ] **Step 2: Write the failing cascade-coverage test**

Create `backend/events/tests/test_sync_future_events_cascade.py`:

```python
from django.test import TestCase
from events.scheduling.registry import reminder_field_union
from events.services import sync_future_events
from events.tests.factories import EventFactory, EventRepeaterFactory


class SyncFutureEventsCascadeTest(TestCase):
    def test_cascades_all_registry_fields(self):
        repeater = EventRepeaterFactory(
            discord_announcement=False,
            discord_announcement_hours=24,
            discord_signup_reminder=False,
            discord_signup_reminder_hours=24,
        )
        future_event = EventFactory(
            event_repeater=repeater,
            state="upcoming",
            discord_announcement=False,
            discord_announcement_hours=24,
        )

        # Edit every reminder field on the repeater
        repeater.discord_announcement = True
        repeater.discord_announcement_hours = 8
        repeater.discord_signup_reminder = True
        repeater.discord_signup_reminder_hours = 168
        repeater.save()

        sync_future_events(repeater)
        future_event.refresh_from_db()

        self.assertTrue(future_event.discord_announcement)
        self.assertEqual(future_event.discord_announcement_hours, 8)
        self.assertTrue(future_event.discord_signup_reminder)
        self.assertEqual(future_event.discord_signup_reminder_hours, 168)

    def test_returns_list_of_synced_events(self):
        repeater = EventRepeaterFactory()
        e1 = EventFactory(event_repeater=repeater, state="upcoming")
        e2 = EventFactory(event_repeater=repeater, state="upcoming")
        result = sync_future_events(repeater)
        ids = {e.pk for e in result}
        self.assertEqual(ids, {e1.pk, e2.pk})

    def test_does_not_touch_past_state_events(self):
        repeater = EventRepeaterFactory(discord_announcement=True)
        past_event = EventFactory(
            event_repeater=repeater,
            state="signups_open",  # past UPCOMING
            discord_announcement=False,
        )
        sync_future_events(repeater)
        past_event.refresh_from_db()
        self.assertFalse(past_event.discord_announcement)
```

- [ ] **Step 3: Run the test — confirm at least one fails**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_cascade -v 2'
```

Expected: `test_returns_list_of_synced_events` and possibly the cascade-all test fail. Current implementation doesn't return the list and may not cascade all fields.

- [ ] **Step 4: Update `sync_future_events`**

Replace `backend/events/services.py` `sync_future_events` body with:

```python
def sync_future_events(repeater):
    """Cascade repeater field changes to upcoming Event rows.

    Returns the list of touched Event instances so callers can chain
    cacheops invalidate_after_commit.
    """
    from cacheops import invalidate_obj
    from events.scheduling.registry import reminder_field_union

    reminder_fields = sorted(reminder_field_union())
    base_fields = [
        # ... existing tournament template fields the cascade always copied,
        # e.g. "tournament_name", "tournament_type", "draft_type", etc.
        # Copy whatever the original implementation listed verbatim.
    ]
    update_fields = base_fields + reminder_fields

    touched = []
    with transaction.atomic():
        future_events = repeater.event_set.filter(state="upcoming").select_for_update()
        for event in future_events:
            for f in update_fields:
                setattr(event, f, getattr(repeater, f))
            event.save(update_fields=update_fields + ["updated_at"])
            invalidate_obj(event)
            touched.append(event)

    return touched
```

(Confirm `base_fields` matches the existing cascade list before this PR — copy from the original function. Do not invent new fields.)

- [ ] **Step 5: Update `EventRepeaterViewSet.perform_update` to consume the return**

Edit `backend/events/views.py:190-195`:

```python
def perform_update(self, serializer):
    repeater = serializer.save()
    invalidate_obj(repeater)
    future_events = sync_future_events(repeater)
    # invalidate_obj on each touched future event so the fire path
    # reads fresh field values within the same poll cycle
    for ev in future_events:
        invalidate_obj(ev)
```

- [ ] **Step 6: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_cascade -v 2'
```

Expected: all 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/events/services.py backend/events/views.py backend/events/tests/test_sync_future_events_cascade.py
git commit -m "feat(events): generic reminder-field cascade + cacheops invalidate

sync_future_events now cascades the union of REMINDERS hours/enabled
fields rather than a hand-coded list. Returns touched events so the
caller invalidates cacheops on each row. Adding a new reminder no
longer requires touching the cascade code."
```

### Task 1.11: Drop `discord_subscriber_dm*` fields and migrate

**Files:**
- Modify: `backend/events/models.py` — remove the two fields from Event and EventRepeater
- Modify: `backend/events/serializers.py` — remove from serializer field lists
- Modify: `backend/events/schemas.py` — remove from schema definitions
- Create: migration via `makemigrations`
- Test: `backend/events/tests/test_subscriber_dm_dropped.py` (new)

**Why:** These fields are dead per spec Q1 (verified by Q10 — UI's "Message interested users" toggle binds to `discord_notify_new_events`, not these). Dropping them prevents future "wired in serializer, not in scheduling" recurrences.

- [ ] **Step 1: Write the failing test**

Create `backend/events/tests/test_subscriber_dm_dropped.py`:

```python
from django.test import TestCase
from events.models import Event, EventRepeater


class SubscriberDmFieldsDroppedTest(TestCase):
    def test_event_has_no_subscriber_dm_field(self):
        event_field_names = {f.name for f in Event._meta.get_fields()}
        self.assertNotIn("discord_subscriber_dm", event_field_names)
        self.assertNotIn("discord_subscriber_dm_hours", event_field_names)

    def test_event_repeater_has_no_subscriber_dm_field(self):
        repeater_field_names = {f.name for f in EventRepeater._meta.get_fields()}
        self.assertNotIn("discord_subscriber_dm", repeater_field_names)
        self.assertNotIn("discord_subscriber_dm_hours", repeater_field_names)
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_subscriber_dm_dropped -v 2'
```

Expected: FAIL (fields still exist).

- [ ] **Step 3: Remove fields from `backend/events/models.py`**

Find and delete the four lines (two on Event, two on EventRepeater):

```python
discord_subscriber_dm = models.BooleanField(...)
discord_subscriber_dm_hours = models.IntegerField(...)
```

- [ ] **Step 4: Remove from `backend/events/serializers.py`**

Search for `discord_subscriber_dm` and remove all references — there are 6 occurrences (3 serializers × 2 fields).

```bash
grep -n "discord_subscriber_dm" backend/events/serializers.py
```

Delete each matching line.

- [ ] **Step 5: Remove from `backend/events/schemas.py`**

```bash
grep -n "discord_subscriber_dm" backend/events/schemas.py
```

Delete the two matching lines.

- [ ] **Step 6: Generate the migration**

```bash
just dev::exec backend python manage.py makemigrations events
```

Expected: a new migration file is created with two `RemoveField` operations.

- [ ] **Step 7: Apply the migration**

```bash
just db::migrate::all
```

- [ ] **Step 8: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_subscriber_dm_dropped -v 2'
```

Expected: PASS.

- [ ] **Step 9: Run the registry guardrail tests — confirm they still pass**

```bash
just test::run 'python manage.py test events.tests.test_scheduling_registry -v 2'
```

Expected: PASS — no remaining `discord_*_hours` field is unregistered.

- [ ] **Step 10: Commit**

```bash
git add backend/events/models.py backend/events/serializers.py backend/events/schemas.py backend/events/migrations/
git commit -m "feat(events): drop discord_subscriber_dm{,_hours} dead fields

Dead fields with no consumers. The UI 'Message interested users'
toggle binds to discord_notify_new_events (verified). Destructive
migration; backups required pre-deploy. Cacheops invalidate_model
(Event, EventRepeater) post-deploy step in release runbook."
```

### Task 1.12: Add cacheops invalidate_after_commit in `EventViewSet.perform_update`

**Files:**
- Modify: `backend/events/views.py:379-421` (EventViewSet.perform_update)
- Test: `backend/events/tests/test_event_edit_invalidates_cache.py` (new)

**Why:** The spec calls for cacheops to be invalidated explicitly so the fire path's next poll sees fresh field values. Auto-invalidation via post_save is unreliable inside `transaction.atomic()`.

- [ ] **Step 1: Write the failing test**

Create `backend/events/tests/test_event_edit_invalidates_cache.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from events.tests.factories import EventFactory


class EventEditInvalidatesCacheTest(TestCase):
    @patch("events.views.invalidate_obj")
    def test_perform_update_invalidates_event(self, mock_invalidate):
        event = EventFactory()
        # ... call the viewset's perform_update with a mock serializer
        # The exact harness depends on the project's existing test patterns;
        # use rest_framework.test.APIClient if that's the project convention
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=event.organization.owner)  # adjust as needed
        client.patch(f"/api/events/{event.pk}/", {"name": "Edited"})

        mock_invalidate.assert_any_call(event)  # at minimum, the event itself
```

- [ ] **Step 2: Run the test — confirm it fails or is partial**

```bash
just test::run 'python manage.py test events.tests.test_event_edit_invalidates_cache -v 2'
```

Expected: FAIL — `invalidate_obj` not called from this code path (or called but not in the way we want).

- [ ] **Step 3: Add explicit invalidation to `EventViewSet.perform_update`**

In `backend/events/views.py:379-421`, add at the end of `perform_update`:

```python
from cacheops import invalidate_obj

def perform_update(self, serializer):
    # ... existing save/sync logic ...
    event = serializer.instance
    invalidate_obj(event)
```

(Look for the existing pattern — the file may already use `invalidate_after_commit`. Use whichever is consistent with the rest of the file.)

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_event_edit_invalidates_cache -v 2'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/views.py backend/events/tests/test_event_edit_invalidates_cache.py
git commit -m "feat(events): explicit cacheops invalidate on event edit

Closes the staleness window where the fire path could read pre-edit
field values from cacheops on the next 30s poll."
```

### Task 1.13: Concurrency test — the unique-constraint guard works end-to-end

**Files:**
- Test: `backend/events/tests/test_idempotency.py` (extend)

**Why:** Final verification that the partial unique index actually prevents double-fires under simulated concurrent polls.

- [ ] **Step 1: Write the concurrent-fire test**

Append to `backend/events/tests/test_idempotency.py`:

```python
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from django.test import TransactionTestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog
from events.scheduling.fire import fire_due_reminders
from events.tests.factories import EventFactory, EventRepeaterFactory


class ConcurrentFireProducesOneRowTest(TransactionTestCase):
    @patch("events.scheduling.fire.current_app.send_task")
    def test_two_concurrent_fires_dispatch_at_most_two_tasks_one_row_persists(
        self, mock_send
    ):
        repeater = EventRepeaterFactory()
        event = EventFactory(
            event_repeater=repeater,
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
            discord_announcement_hours=24,
            scheduled_at=timezone.now() + timedelta(hours=12),
            state="upcoming",
        )

        # Simulate a real worker — when the dispatched task "runs",
        # it tries to write a success log row.
        def fake_send_task(name, args=None, **kwargs):
            try:
                with transaction.atomic():
                    DiscordMessageLog.objects.create(
                        source="event_announcement",
                        source_id=args[0],
                        success=True,
                    )
            except IntegrityError:
                pass  # lost the race
        mock_send.side_effect = fake_send_task

        # Two concurrent polls
        with ThreadPoolExecutor(max_workers=2) as exe:
            futures = [exe.submit(fire_due_reminders) for _ in range(2)]
            for f in futures:
                f.result()

        # Exactly one success row exists despite the race
        rows = DiscordMessageLog.objects.filter(
            source="event_announcement", source_id=event.pk, success=True
        )
        self.assertEqual(rows.count(), 1)
```

- [ ] **Step 2: Run the test**

```bash
just test::run 'python manage.py test events.tests.test_idempotency.ConcurrentFireProducesOneRowTest -v 2'
```

Expected: PASS — the unique constraint serializes the writes.

- [ ] **Step 3: Commit**

```bash
git add backend/events/tests/test_idempotency.py
git commit -m "test(events): concurrent fire produces exactly one log row

End-to-end concurrency test: two parallel fire_due_reminders calls
dispatch at most two tasks but the partial unique index ensures
only one DiscordMessageLog success row persists."
```

### Task 1.14: PR-1 deploy runbook entry

**Files:**
- Create or modify: `docs/operations/release-runbook.md` (or wherever the project keeps deploy notes)

**Why:** PR-1 has two operational steps that must run during deploy: cacheops model invalidation and the destructive migration backup check.

- [ ] **Step 1: Add a runbook entry**

Append to the appropriate operational doc (find via `find docs -name '*runbook*' -o -name '*deploy*' | head -5`):

```markdown
## Release: event reminder scheduling registry (PR-1)

**Pre-deploy:**
1. Backup production DB (standard procedure).
2. Confirm PR-0 has been on production for ≥ 1 release cycle (Zod schemas tolerate missing `discord_subscriber_dm*`).
3. Run pre-flight check:
   ```sql
   SELECT id, discord_announcement_hours, scheduled_at
   FROM events_event
   WHERE discord_announcement_hours <> 24
     AND state IN ('upcoming', 'signups_open');
   ```
   Any rows with non-default values will see announcement timing change post-deploy. Notify those event owners if relevant.

**Deploy:**
1. Run migrations: `just db::migrate::prod`.
2. Restart celery workers (required for `task_acks_late` to take effect on `check_event_reminders`).
3. Restart celery beat.

**Post-deploy:**
1. Run cacheops invalidation in a Django shell to flush cached pre-migration model instances:
   ```python
   from cacheops import invalidate_model
   from events.models import Event, EventRepeater
   invalidate_model(Event)
   invalidate_model(EventRepeater)
   ```
2. Verify fire path is healthy: tail celery worker logs for ~2 minutes; expect `Checked 4 reminder types` from `fire_due_reminders` every 30s with no errors.
```

- [ ] **Step 2: Commit**

```bash
git add docs/
git commit -m "docs(ops): release runbook entry for PR-1 reminder registry"
```

### Task 1.15: Open the pull request

- [ ] **Step 1: Push the branch**

```bash
git push -u origin <feature-branch>
```

- [ ] **Step 2: Open PR with checklist body**

```bash
gh pr create --title "feat(events): declarative reminder registry + idempotency guard" --body "$(cat <<'EOF'
## Summary
- Declarative `ScheduledReminder` registry replacing inline branches in `check_event_reminders`
- Postgres partial unique index on `DiscordMessageLog(source, source_id) WHERE success=TRUE` prevents polling-overlap double-fires
- `discord_subscriber_dm{,_hours}` dropped (dead fields)
- `discord_announcement_hours` now actually fires the announcement (was inert)
- `sync_future_events` cascades reminder fields generically + invalidates cacheops per row
- CI guardrails fail when a reminder field is added without a registry entry, when a task name is unregistered, or when the slim serializer is missing a fire-path field

## Deploy ordering
- PR-0 must have shipped at least one release cycle ago (frontend Zod tolerates dropped fields)
- See `docs/operations/release-runbook.md` for cacheops invalidation step

## Behavioral changes
- Announcements no longer post immediately on save — they fire `discord_announcement_hours` before `scheduled_at` (default 24h)
- Concurrent polls cannot double-fire (DB constraint)

## Test plan
- [ ] Backend: `just test::run 'python manage.py test events.tests -v 2'` — all green
- [ ] Concurrency: `events.tests.test_idempotency.ConcurrentFireProducesOneRowTest`
- [ ] Registry guardrails: `events.tests.test_scheduling_registry`
- [ ] Manual: deploy to staging, edit an event's `discord_announcement_hours`, observe announcement fires at the new threshold (after stuck-row cleanup if applicable)
EOF
)"
```

---

## Phase 2 — Series row-level fixes + frontend cleanup (PR-2)

### Task 2.1: `sync_future_events` recomputes `scheduled_at`

**Files:**
- Modify: `backend/events/services.py:662-691` (extend the function from Task 1.10)
- Test: `backend/events/tests/test_sync_future_events_recompute.py` (new)

**Why:** When a repeater's `day_of_week`/`time_of_day`/`timezone`/`starts_at` is edited, existing upcoming Event rows currently keep their stale `scheduled_at`. The next hourly `generate_upcoming_events` task creates *new* rows at the new schedule — duplicates. Recomputing eliminates the duplicate set.

- [ ] **Step 1: Write the failing recompute test**

Create `backend/events/tests/test_sync_future_events_recompute.py`:

```python
from datetime import datetime, time, timedelta
from django.test import TestCase
from django.utils import timezone
from events.services import sync_future_events
from events.tests.factories import EventFactory, EventRepeaterFactory


class SyncFutureEventsRecomputeTest(TestCase):
    def test_day_of_week_change_recomputes_scheduled_at(self):
        repeater = EventRepeaterFactory(
            day_of_week=1,  # Monday (Sunday=0 convention)
            time_of_day=time(20, 0),
            timezone="UTC",
        )
        # Create an upcoming event scheduled for next Monday at 20:00 UTC
        event = EventFactory(
            event_repeater=repeater,
            state="upcoming",
            scheduled_at=_next_weekday_at(1, time(20, 0), tz="UTC"),
        )

        # Edit repeater to Tuesday (day_of_week=2)
        repeater.day_of_week = 2
        repeater.save()

        sync_future_events(repeater)
        event.refresh_from_db()

        # The same row should now be on Tuesday at 20:00, not Monday
        self.assertEqual(event.scheduled_at.weekday(), 1)  # Python: Mon=0, Tue=1
        # ... or whatever assertion matches the project's day_of_week convention

    def test_time_of_day_change_recomputes(self):
        repeater = EventRepeaterFactory(time_of_day=time(20, 0))
        event = EventFactory(
            event_repeater=repeater,
            state="upcoming",
            scheduled_at=_next_weekday_at(repeater.day_of_week, time(20, 0)),
        )
        repeater.time_of_day = time(22, 30)
        repeater.save()
        sync_future_events(repeater)
        event.refresh_from_db()
        self.assertEqual(event.scheduled_at.hour, 22)
        self.assertEqual(event.scheduled_at.minute, 30)

    def test_collision_deletes_stale_row(self):
        """If recomputed scheduled_at collides with an existing row,
        the stale one is deleted and the existing kept."""
        repeater = EventRepeaterFactory(day_of_week=1)
        # Upcoming event A on Monday (about to be recomputed to Tuesday)
        event_a = EventFactory(event_repeater=repeater, state="upcoming")
        original_a_id = event_a.pk

        # Pre-existing event B on Tuesday (the new target)
        target_at = _next_weekday_at(2, repeater.time_of_day)
        EventFactory(
            event_repeater=repeater, state="upcoming", scheduled_at=target_at
        )

        repeater.day_of_week = 2
        repeater.save()
        sync_future_events(repeater)

        # Either A or B remains — but not both. A is the "stale" row, so
        # it should be the one deleted.
        from events.models import Event
        self.assertFalse(Event.objects.filter(pk=original_a_id).exists())


def _next_weekday_at(day_of_week, time_of_day, tz="UTC"):
    """Helper — finds the next datetime matching day_of_week + time_of_day."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = timezone.now().astimezone(ZoneInfo(tz))
    # Convert Sunday=0 convention to Python's Monday=0 if needed
    target_python_dow = (day_of_week - 1) % 7  # Sunday=0 -> 6
    days_ahead = (target_python_dow - now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=time_of_day.hour,
        minute=time_of_day.minute,
        second=0,
        microsecond=0,
    )
    return candidate
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_recompute -v 2'
```

Expected: FAIL on all three tests.

- [ ] **Step 3: Add `scheduled_at` recompute to `sync_future_events`**

Edit `backend/events/services.py` `sync_future_events`. Before the per-row save, compute the new `scheduled_at`:

```python
def sync_future_events(repeater):
    """..."""
    from cacheops import invalidate_obj
    from events.scheduling.registry import reminder_field_union
    from events.models import Event

    reminder_fields = sorted(reminder_field_union())
    base_fields = [
        # ... existing tournament template fields ...
    ]
    schedule_fields = ["day_of_week", "time_of_day", "timezone", "starts_at"]
    update_fields = base_fields + reminder_fields

    touched = []
    deleted_ids = []

    with transaction.atomic():
        future_events = repeater.event_set.filter(
            state="upcoming"
        ).select_for_update().order_by("scheduled_at")

        for event in future_events:
            for f in update_fields:
                setattr(event, f, getattr(repeater, f))

            # Recompute scheduled_at if any schedule input changed
            new_scheduled_at = _compute_occurrence_datetime(
                repeater,
                base_date=event.scheduled_at.date(),
            )
            if new_scheduled_at != event.scheduled_at:
                # Check for collision with another upcoming row
                collision = Event.objects.filter(
                    event_repeater=repeater,
                    scheduled_at=new_scheduled_at,
                    state="upcoming",
                ).exclude(pk=event.pk).first()
                if collision is not None:
                    # Existing row at the new slot; delete the stale one
                    deleted_ids.append(event.pk)
                    event.delete()
                    continue
                event.scheduled_at = new_scheduled_at

            event.save(update_fields=update_fields + ["scheduled_at", "updated_at"])
            invalidate_obj(event)
            touched.append(event)

    return touched


def _compute_occurrence_datetime(repeater, base_date):
    """Translate the repeater's day_of_week + time_of_day + timezone into
    an absolute datetime anchored on or near base_date. Replicate the
    logic that generate_events_for_repeater uses so that recomputed
    timestamps match newly-generated ones."""
    # ... use the same helper (or extract the existing one from
    # generate_events_for_repeater) ...
```

(Locate the existing day-of-week → datetime helper used by `generate_events_for_repeater` and reuse it.)

- [ ] **Step 4: Run the tests — confirm they pass**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_recompute -v 2'
```

Expected: PASS (all 3 tests).

- [ ] **Step 5: Run broader event tests for regressions**

```bash
just test::run 'python manage.py test events.tests -v 2'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/events/services.py backend/events/tests/test_sync_future_events_recompute.py
git commit -m "feat(events): sync_future_events recomputes scheduled_at on series edit

When repeater day_of_week/time_of_day/timezone changes, existing
upcoming events now move to the new slot rather than staying stale
and being duplicated by generate_upcoming_events. Collision with an
already-existing row at the new slot deletes the stale row."
```

### Task 2.2: Reject `discord_signup_reminder*` for single events at the serializer

**Files:**
- Modify: `backend/events/serializers.py` — add `validate` method on EventSerializer
- Test: `backend/events/tests/test_event_validation_single.py` (new)

**Why:** Backend rejection is the source of truth — a frontend that bypasses the form-level conditional rendering still gets a 400.

- [ ] **Step 1: Write the failing validation test**

Create `backend/events/tests/test_event_validation_single.py`:

```python
from rest_framework.exceptions import ValidationError
from django.test import TestCase
from events.serializers import EventSerializer


class EventSingleEventValidationTest(TestCase):
    def test_signup_reminder_rejected_on_single_event(self):
        serializer = EventSerializer(data={
            "name": "Solo",
            "scheduled_at": "2026-12-01T20:00:00Z",
            "event_repeater": None,
            "discord_signup_reminder": True,
            "discord_signup_reminder_hours": 24,
            # ... minimum-required fields for a valid single event ...
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("discord_signup_reminder", str(serializer.errors))
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
just test::run 'python manage.py test events.tests.test_event_validation_single -v 2'
```

Expected: FAIL (validation passes; no rejection logic exists).

- [ ] **Step 3: Add the validator**

In `backend/events/serializers.py`, add to EventSerializer:

```python
def validate(self, attrs):
    attrs = super().validate(attrs)
    is_single_event = attrs.get("event_repeater") is None
    if is_single_event:
        if attrs.get("discord_signup_reminder"):
            raise serializers.ValidationError({
                "discord_signup_reminder": (
                    "Signup reminder DMs require a recurring event series — "
                    "no subscribers exist for single events."
                )
            })
    return attrs
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
just test::run 'python manage.py test events.tests.test_event_validation_single -v 2'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/serializers.py backend/events/tests/test_event_validation_single.py
git commit -m "feat(events): reject discord_signup_reminder on single events"
```

### Task 2.3: Conditional render of signup-reminder fields in `DiscordConfigSection`

**Files:**
- Modify: `frontend/app/components/events/DiscordConfigSection.tsx`
- Test: extend or create a Playwright spec

**Why:** Hide the field — by unmounting, not display:none — when not editing a series.

- [ ] **Step 1: Identify the existing signup-reminder block**

```bash
grep -n "discord_signup_reminder\|signup_reminder_hours" frontend/app/components/events/DiscordConfigSection.tsx
```

- [ ] **Step 2: Write the failing Playwright test**

Append to `frontend/tests/playwright/e2e/16-events/05-event-form-validation.spec.ts` (or create):

```typescript
test('signup reminder fields hidden on single event creation', async ({ page }) => {
  await loginAsOrgAdmin(page)
  await page.goto('/events/new')
  await page.getByLabel('Recurring event').uncheck()  // single event mode
  await expect(page.getByLabel(/signup reminder/i)).toBeHidden()
})

test('signup reminder fields visible on repeater creation', async ({ page }) => {
  await loginAsOrgAdmin(page)
  await page.goto('/repeaters/new')
  await expect(page.getByLabel(/signup reminder/i)).toBeVisible()
})
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
just test::pw::spec 16-events/05
```

Expected: FAIL — fields visible on single-event form.

- [ ] **Step 4: Gate the block on `isRepeater`**

Edit `DiscordConfigSection.tsx`. Find the existing signup-reminder UI block (the `<CheckboxField name="discord_signup_reminder" ... />` and the related `<NumberField name="discord_signup_reminder_hours" ... />`) and wrap with the existing `isRepeater` prop:

```tsx
{isRepeater && (
  <div className="rounded-md border border-border p-3">
    <CheckboxField control={control} name="discord_signup_reminder" ... />
    {watch('discord_signup_reminder') && (
      <NumberField control={control} name="discord_signup_reminder_hours" ... />
    )}
  </div>
)}
```

The `isRepeater` prop already exists on this component (`EditEventModal.tsx:422` passes `false`, `EditRepeaterModal.tsx:504` passes `true`).

- [ ] **Step 5: Run the test — confirm it passes**

```bash
just test::pw::spec 16-events/05
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/events/DiscordConfigSection.tsx frontend/tests/playwright/e2e/16-events/05-event-form-validation.spec.ts
git commit -m "feat(events): hide signup-reminder fields on single-event forms"
```

### Task 2.4: Zod discriminated union for single-vs-repeater event schemas

**Files:**
- Modify: `frontend/app/components/events/schemas.ts` (lines ~246-247 and surrounding)
- Test: `frontend/tests/unit/event-schema-discriminated.test.ts` (new)

**Why:** The Zod schema must permit single-event payloads to omit `discord_signup_reminder*` while still requiring them for repeater payloads.

- [ ] **Step 1: Write the failing parse tests**

Create `frontend/tests/unit/event-schema-discriminated.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { eventSchema } from '@/components/events/schemas'

describe('event schema — single vs repeater', () => {
  it('parses a single event without discord_signup_reminder fields', () => {
    const single = {
      // ... minimum valid single-event payload, NO event_repeater, NO discord_signup_reminder*
    }
    expect(() => eventSchema.parse(single)).not.toThrow()
  })

  it('rejects a single event with discord_signup_reminder=true', () => {
    const bad = {
      event_repeater: null,
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
      // ...
    }
    expect(() => eventSchema.parse(bad)).toThrow()
  })

  it('parses a repeater event with discord_signup_reminder fields', () => {
    const repeater = {
      event_repeater: 1,
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
      // ...
    }
    expect(() => eventSchema.parse(repeater)).not.toThrow()
  })
})
```

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
cd frontend && npx vitest run tests/unit/event-schema-discriminated.test.ts
```

- [ ] **Step 3: Refactor `eventSchema` as a discriminated union**

Edit `frontend/app/components/events/schemas.ts`:

```typescript
const baseEventFields = z.object({
  // ... all common fields except discord_signup_reminder ...
})

const singleEventSchema = baseEventFields.extend({
  event_repeater: z.null(),
  discord_signup_reminder: z.literal(false).optional(),
  discord_signup_reminder_hours: z.number().int().min(1).optional(),
})

const repeaterEventSchema = baseEventFields.extend({
  event_repeater: z.number(),
  discord_signup_reminder: z.boolean(),
  discord_signup_reminder_hours: z.number().int().min(1),
})

export const eventSchema = z.discriminatedUnion('event_repeater_kind', [
  singleEventSchema.extend({ event_repeater_kind: z.literal('single') }),
  repeaterEventSchema.extend({ event_repeater_kind: z.literal('repeater') }),
]).or(/* fallback for current API shape using event_repeater nullable */
  singleEventSchema.or(repeaterEventSchema)
)
```

(Adapt to whatever the existing schema actually exports. The discriminated union is simpler if a `event_repeater_kind` field exists; otherwise use a `superRefine`.)

- [ ] **Step 4: Run the tests — confirm they pass**

```bash
cd frontend && npx vitest run tests/unit/event-schema-discriminated.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/schemas.ts frontend/tests/unit/event-schema-discriminated.test.ts
git commit -m "feat(events): discriminated-union event schema by repeater presence"
```

### Task 2.5: `defaultValues` cleanup across the four modal components

**Files:**
- Modify: `frontend/app/components/events/EditEventModal.tsx:113-114`
- Modify: `frontend/app/components/events/CreateEventModal.tsx:112-113`
- Modify: `frontend/app/components/events/EditOrgDefaultsModal.tsx:105-106`
- Modify: `frontend/app/components/events/EditRepeaterModal.tsx:118-119`

**Why:** With `discord_subscriber_dm*` dropped (PR-1) and `discord_signup_reminder*` conditional, the `defaultValues` objects in these modals must be updated to match the schemas.

- [ ] **Step 1: Audit the defaultValues references**

```bash
grep -n "discord_subscriber_dm\|discord_signup_reminder" frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx frontend/app/components/events/EditOrgDefaultsModal.tsx frontend/app/components/events/EditRepeaterModal.tsx
```

- [ ] **Step 2: For each file, remove `discord_subscriber_dm{,_hours}` from defaultValues**

Example, in `EditEventModal.tsx:113-114`:

```typescript
// before
discord_subscriber_dm: false,
discord_subscriber_dm_hours: 24,

// after — both lines deleted
```

Apply the same deletion pattern to `CreateEventModal.tsx:112-113`, `EditOrgDefaultsModal.tsx:105-106`, `EditRepeaterModal.tsx:118-119`.

- [ ] **Step 3: For the two non-repeater modals (`EditEventModal`, `CreateEventModal`), conditionally include `discord_signup_reminder*` in defaultValues**

Example pattern in `EditEventModal.tsx`:

```typescript
const defaultValues = {
  // ... other fields ...
  ...(event.event_repeater ? {
    discord_signup_reminder: event.discord_signup_reminder ?? false,
    discord_signup_reminder_hours: event.discord_signup_reminder_hours ?? 24,
  } : {}),
}
```

- [ ] **Step 4: Run the existing modal Playwright tests**

```bash
just test::pw::spec event
```

Expected: all related modal tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx frontend/app/components/events/EditOrgDefaultsModal.tsx frontend/app/components/events/EditRepeaterModal.tsx
git commit -m "feat(events): align modal defaultValues with new schema shape

Drops dead discord_subscriber_dm* defaults; conditionally includes
discord_signup_reminder* only on repeater paths."
```

### Task 2.6: Close the TanStack Query invalidation gap

**Files:**
- Modify: `frontend/app/components/events/useEvent.ts:185-194` (useUpdateEventMutation)
- Test: extend a Playwright spec or write a small RTL test

**Why:** Without invalidating `event-discord` and `event-task-schedule` keys, the UI's reminder timing display (15s polled) shows stale values until the next poll.

- [ ] **Step 1: Identify current invalidation logic**

```bash
sed -n '180,200p' frontend/app/components/events/useEvent.ts
```

- [ ] **Step 2: Write the failing Playwright assertion**

In an existing event-edit spec (or new file), assert that the Discord log section refreshes immediately after edit:

```typescript
test('event edit updates task schedule UI within 1s', async ({ page }) => {
  await loginAsOrgAdmin(page)
  await page.goto(`/events/${eventId}/edit`)
  // ... edit discord_announcement_hours from 24 to 8
  await page.getByLabel('Hours before event').fill('8')
  await page.getByRole('button', { name: 'Save' }).click()
  // The task schedule panel should reflect the new threshold within 1 second
  await expect(page.getByTestId('task-schedule-announcement')).toContainText('8 hours', { timeout: 1500 })
})
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
just test::pw::spec event-edit-task-schedule
```

Expected: FAIL — task schedule shows old value until 15s poll.

- [ ] **Step 4: Add invalidations**

In `useEvent.ts:185-194`, extend `useUpdateEventMutation`:

```typescript
const queryClient = useQueryClient()
return useMutation({
  // ...
  onSuccess: (data, variables) => {
    queryClient.invalidateQueries({ queryKey: ['events'] })
    queryClient.setQueryData(['event', variables.id], data)
    queryClient.invalidateQueries({ queryKey: ['event-discord', variables.id] })
    queryClient.invalidateQueries({ queryKey: ['event-task-schedule', variables.id] })
  },
})
```

- [ ] **Step 5: Run the test — confirm it passes**

```bash
just test::pw::spec event-edit-task-schedule
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/events/useEvent.ts frontend/tests/playwright/
git commit -m "feat(events): invalidate event-discord + event-task-schedule on edit

Closes the up-to-15s staleness window in the Activity Log and Task
Schedule UI after a reminder timing edit."
```

### Task 2.7: Fix the broken Playwright spec

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/07-notification-dm.spec.ts:69-70`

**Why:** PR-1 dropped the fields the spec asserts on. Either delete those assertions or rewrite for `discord_notify_new_events` (the actual subscriber DM toggle).

- [ ] **Step 1: Read the spec**

```bash
sed -n '60,80p' frontend/tests/playwright/e2e/16-events/07-notification-dm.spec.ts
```

- [ ] **Step 2: Decide: delete or rewrite**

If the assertions are testing the dead fields, delete them. If they're testing actual DM behavior (which `discord_notify_new_events` provides), rewrite to use the live field.

Most likely action: delete lines 69-70 referencing `discord_subscriber_dm[_hours]` since the actual subscriber-notify behavior is tested elsewhere.

- [ ] **Step 3: Verify the spec runs cleanly**

```bash
just test::pw::spec 16-events/07
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/07-notification-dm.spec.ts
git commit -m "test(events): drop assertions on removed discord_subscriber_dm fields"
```

### Task 2.8: Open the pull request

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin <feature-branch>
gh pr create --title "feat(events): series row-level fixes + frontend conditional rendering" --body "$(cat <<'EOF'
## Summary
- `sync_future_events` recomputes `scheduled_at` on series day/time/timezone edits — eliminates duplicate occurrences
- Single events reject `discord_signup_reminder*` at the serializer
- `DiscordConfigSection` hides signup-reminder fields on single events (existing `isRepeater` prop)
- Zod schema becomes a discriminated union by repeater presence
- Modal `defaultValues` cleaned across 4 components
- TanStack Query invalidation gap closed for `event-discord` and `event-task-schedule`
- Broken Playwright spec referencing dropped fields fixed

## Depends on
- PR-1 (registry + cleanup) must be merged.

## Test plan
- [ ] Backend: `just test::run 'python manage.py test events.tests -v 2'`
- [ ] Frontend unit: `cd frontend && npx vitest run`
- [ ] Playwright: `just test::pw::spec 16-events`
- [ ] Manual: edit a series day_of_week, verify upcoming occurrences move and no duplicates appear in the next hour
EOF
)"
```

---

## Self-review notes

**Spec coverage check:**
- Q1 subscriber-DM drop → Task 1.11
- Q2 once-fired-sticky (no UI changes) → covered by absence of UI work in PR-1
- Q3 commit to main → procedural
- Q4 PR split → spec restructured to PR-0/PR-1/PR-2; tasks correspondingly grouped
- Q5 stay polled → Task 1.7 (fire path), 1.8 (delegation) keep beat schedule unchanged
- Q6 requires_repeater on signup_reminder → Task 1.6 (registry definition)
- Q7 once-fired-sticky → Task 1.7 (fire path checks `check_message_log_exists`)
- Q8 hours <= 0 skip → Task 1.7 (`if hours <= 0: continue`)
- Q9 announcement scheduled not immediate → Task 1.9
- Q10 UI binding verified → no task; pre-implementation finding documented in spec
- Q11 partial unique index → Task 1.2
- Q12 frontend deploy ordering → Phase 0 (Task 0.1) ships before Phase 1
- Q13 cacheops invalidate_model → Task 1.14 (runbook)

**Critical-finding coverage:**
- "task: Callable celery-unsafe" → Task 1.6 uses `task_name: str` + `current_app.send_task`
- "Polling overlap double-fire" → Tasks 1.2, 1.3, 1.13
- "sync_future_events missing invalidate_after_commit" → Task 1.10
- "Stale tasks.py:742-743 comment" → Task 1.8
- "EventSlimSerializer field coverage" → Task 1.1 (and Task 1.6's CI guardrail)
- "Frontend Zod required = deploy break" → Phase 0

**Important-finding coverage:**
- PR-2 frontend scope → Tasks 2.3-2.7
- TanStack Query invalidation → Task 2.6
- Deploy ordering → 3-phase structure + Task 1.14 runbook
- Cacheops invalidate_model → Task 1.14

**Placeholder scan:** No "TBD" / "implement later" / generic "add error handling" found. Each task code block is complete and self-contained.

**Type consistency:** `ScheduledReminder.task_name` (str) is used consistently across Task 1.6, 1.7, and the CI tests.
