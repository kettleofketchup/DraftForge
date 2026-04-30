# Event reminder scheduling registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc reminder polling with a declarative `ScheduledReminder` registry, eliminate dead reminder fields, prevent polling-overlap double-fires via a DB unique constraint, and fix series-edit bugs that cause duplicate occurrences and "wrong day" reminder firings.

**Architecture:** A `scheduling/registry.py` module declares all reminder types as data; `scheduling/fire.py` iterates the registry on each 30-second beat poll. Once-fired-sticky semantics — `DiscordMessageLog` rows gate re-fires permanently. A pre-send lease pattern on `DiscordMessageLog` (full unique index on `(source, source_id)`, nullable `success`, `claimed_at`) ensures only one worker reaches the Discord HTTP send under concurrent-task races; a 5-minute sweeper reaps leases stuck from worker crashes. `sync_future_events` cascades reminder fields generically (union of `REMINDERS` field names) and calls `invalidate_after_commit` to keep cacheops in sync. The announcement reminder, currently inert, is wired through the registry.

**Tech Stack:** Django 5, Django REST Framework, Celery 5, django-cacheops (Redis), Daphne (Channels), React 19 + TypeScript, Zod, TanStack Query, Playwright. Backend tests via `just test::run`, frontend tests via `just test::pw::spec`.

**Spec:** `docs/superpowers/specs/2026-04-30-event-reminder-scheduling-registry-design.md` (decisions Q1–Q13 are normative)

**Three-phase rollout:**

- **Phase 0 (PR-0)** — frontend Zod loosen. One file. Ships first, sits one release cycle.
- **Phase 1 (PR-1)** — registry + dead-field cleanup + idempotency guard. Backend-heavy. Ships after PR-0 has cycled.
- **Phase 2 (PR-2)** — series row-level fixes + frontend cleanup. Ships after PR-1.

Each phase produces deployable, testable software on its own.

---

## Phase 0 — Frontend Zod loosen (PR-0)

### Task 0.1: Loosen Zod schemas + clean up TS interfaces, DISCORD_CONFIG_DEFAULTS, and modal `reset()` for `discord_subscriber_dm*`

**Files:**
- Modify: `frontend/app/components/events/schemas.ts` — Zod schemas at lines ~84-85 and ~260-261 (make optional), AND the `DISCORD_CONFIG_DEFAULTS` constant at lines ~270-298 (delete the two lines for the dropped fields)
- Modify: `frontend/app/components/api/eventsAPI.ts` — `EventRepeaterType` interface at lines ~183-184 and `OrgEventDefaultsType` interface at lines ~263-264 (make optional). Note the file path is `components/api/`, not `app/api/`. There is no `Event` interface in this file (`EventType` is exported from Zod via the schemas).
- Modify: `frontend/app/components/events/EditEventModal.tsx`, `CreateEventModal.tsx`, `EditOrgDefaultsModal.tsx`, `EditRepeaterModal.tsx` — remove `discord_subscriber_dm{,_hours}` from each `reset()` call inside `useEffect`. The modals' `defaultValues` use `...DISCORD_CONFIG_DEFAULTS` (already cleaned in `schemas.ts`), so the only modal-side cleanup is the `reset()` calls.
- Test: `frontend/app/components/events/__tests__/schemas.test.ts` (new — co-located)

**Why:** PR-1 will drop `discord_subscriber_dm` and `discord_subscriber_dm_hours` from backend Event/EventRepeater. The Zod schemas, TS interfaces, and modal defaultValues all reference these fields as required. Loosening only Zod (without the TS + modal cleanup) makes `event.discord_subscriber_dm` typed `boolean | undefined` while consumers still treat it as `boolean` — `tsc` breaks. PR-0 ships all four together so the frontend tolerates the missing fields cleanly *and* compiles.

- [ ] **Step 1: Verify vitest can pick up co-located test files**

```bash
cat frontend/vitest.config.ts | grep -A2 'include\|test'
```

Expected: include glob is `app/**/*.test.ts` (or similar). If tests at `frontend/tests/unit/` are NOT in the include glob, the test file MUST be co-located or the include glob extended. This task assumes co-location at `frontend/app/components/events/__tests__/schemas.test.ts`.

- [ ] **Step 2: Confirm the project's TypeScript path alias**

```bash
cat frontend/tsconfig.json | grep -A3 '"paths"'
```

Expected: `~/*` mapped to `app/*` (DraftForge convention). Use `~/components/...` in test imports, NOT `@/components/...`.

- [ ] **Step 3: Read the current schema and consumer surface**

```bash
grep -rn "discord_subscriber_dm" frontend/app/components/events/schemas.ts frontend/app/components/api/eventsAPI.ts frontend/app/components/events/*.tsx
```

Expected: **6 lines in `schemas.ts`** (4 for the Zod schemas at 84-85 and 260-261, 2 for DISCORD_CONFIG_DEFAULTS at 290-291); **4 lines in `eventsAPI.ts`** (`EventRepeaterType` 183-184, `OrgEventDefaultsType` 263-264); **4 lines across the four modal `reset()` calls**.

- [ ] **Step 4: Write the failing parse test**

Create `frontend/app/components/events/__tests__/schemas.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { eventSchema, discordConfigSchema } from '~/components/events/schemas'

const baseDiscordConfig = {
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

describe('discord_subscriber_dm tolerance', () => {
  it('discordConfigSchema parses payload missing the dropped fields', () => {
    expect(() => discordConfigSchema.parse(baseDiscordConfig)).not.toThrow()
  })

  it('discordConfigSchema also parses payloads that still include the fields', () => {
    expect(() => discordConfigSchema.parse({
      ...baseDiscordConfig,
      discord_subscriber_dm: true,
      discord_subscriber_dm_hours: 24,
    })).not.toThrow()
  })
})
```

- [ ] **Step 5: Run the test — confirm it fails**

```bash
cd frontend && npx vitest run app/components/events/__tests__/schemas.test.ts
```

Expected: FAIL with `discord_subscriber_dm: Required` and `discord_subscriber_dm_hours: Required`.

- [ ] **Step 6: Loosen the Zod schema**

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

- [ ] **Step 7: Clean up `DISCORD_CONFIG_DEFAULTS` constant**

Edit `frontend/app/components/events/schemas.ts` at lines ~270-298. The constant is spread into every modal's `defaultValues`. Delete the two lines:

```typescript
discord_subscriber_dm: false,            // delete
discord_subscriber_dm_hours: 24,          // delete
```

- [ ] **Step 8: Update the TS interfaces in `frontend/app/components/api/eventsAPI.ts`**

At lines ~183-184 (`EventRepeaterType` interface):

```typescript
// before
discord_subscriber_dm: boolean;
discord_subscriber_dm_hours: number;

// after
discord_subscriber_dm?: boolean;
discord_subscriber_dm_hours?: number;
```

Same change at lines ~263-264 (`OrgEventDefaultsType` interface).

(There is no `Event` interface in this file — `EventType` is exported from Zod by `schemas.ts`. Loosening the Zod schema in Step 6 already updated `EventType`'s inferred shape.)

- [ ] **Step 9: Remove from modal `reset()` calls**

The modals get their initial values from `...DISCORD_CONFIG_DEFAULTS` (already cleaned in Step 7), so `defaultValues` doesn't need a manual edit. The `reset(...)` calls inside `useEffect` DO mention the dropped fields directly — those are what need editing.

For each modal, find the `reset({ ... })` call inside `useEffect` and delete the two lines:

```typescript
discord_subscriber_dm: event.discord_subscriber_dm,
discord_subscriber_dm_hours: event.discord_subscriber_dm_hours,
```

Files and approximate lines (the `reset()` call line range, not the `defaultValues` range):
- `frontend/app/components/events/EditEventModal.tsx:125-126`
- `frontend/app/components/events/CreateEventModal.tsx:124-125`
- `frontend/app/components/events/EditOrgDefaultsModal.tsx:117-118`
- `frontend/app/components/events/EditRepeaterModal.tsx:131-132`

- [ ] **Step 10: Run the test — confirm it passes**

```bash
cd frontend && npx vitest run app/components/events/__tests__/schemas.test.ts
```

Expected: PASS.

- [ ] **Step 11: Run TypeScript type-check across the frontend**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors. If errors surface for `event.discord_subscriber_dm` access in any component (the fields' new type is `boolean | undefined`), update those consumers with a `?? false` fallback.

- [ ] **Step 12: Run the full Playwright event-form suite**

```bash
just test::pw::spec event-form
```

Expected: all existing tests pass — making fields optional and removing them from defaults is strictly more permissive.

- [ ] **Step 13: Commit**

```bash
git add frontend/app/components/events/schemas.ts frontend/app/components/api/eventsAPI.ts frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx frontend/app/components/events/EditOrgDefaultsModal.tsx frontend/app/components/events/EditRepeaterModal.tsx frontend/app/components/events/__tests__/schemas.test.ts
git commit -m "feat(events): drop discord_subscriber_dm from frontend surface

Zod schemas, TS interfaces, DISCORD_CONFIG_DEFAULTS constant, and the
four modals' reset() calls all become tolerant of these fields'
absence. Prep for PR-1's backend column drop. Sits one release cycle
on production before PR-1."
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

### Task 1.2: `DiscordMessageLog` lease-pattern schema migration

**Files:**
- Modify: `backend/discordbot/models.py` — `DiscordMessageLog` (line ~85)
- Create: `backend/discordbot/migrations/0XXX_discord_message_log_lease_schema.py`
- Test: `backend/events/tests/test_idempotency.py` (new file)

**Why:** The lease pattern (Q11, Option B) requires three schema changes: `success` becomes nullable (NULL = pending lease), a new `claimed_at` timestamp lets a sweeper reap stuck leases, and a **partial** unique index on `(source, source_id) WHERE success IS NOT FALSE` serializes claim attempts while leaving `success=False` rows reclaimable for retry. The constraint catches the second worker's claim BEFORE the Discord HTTP send — preventing duplicate messages, not just duplicate audit rows.

- [ ] **Step 1: Confirm `DiscordMessageLog` field shape**

```bash
sed -n '85,135p' backend/discordbot/models.py
```

Expected: model has `source`, `source_id`, `success` (BooleanField, currently non-nullable at line 96), plus required `channel_id` (CharField) and `embed_data` (JSONField). No `claimed_at` yet. The required `channel_id` and `embed_data` are exactly the fields the worker passes at claim time (Option B), so the lease row is fully populated from creation.

- [ ] **Step 2: Write the failing schema-shape test**

Create `backend/events/tests/test_idempotency.py`:

```python
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog


def _row(**overrides):
    """Helper — DiscordMessageLog requires channel_id and embed_data."""
    defaults = dict(
        channel_id="ch_1",
        embed_data={"title": "test"},
        success=None,
        claimed_at=timezone.now(),
    )
    defaults.update(overrides)
    return DiscordMessageLog.objects.create(**defaults)


class DiscordMessageLogLeaseSchemaTest(TransactionTestCase):
    def test_success_field_is_nullable(self):
        row = _row(source="signup_reminder", source_id=1, success=None)
        self.assertIsNone(row.success)

    def test_claimed_at_field_exists(self):
        row = _row(source="signup_reminder", source_id=2)
        self.assertIsNotNone(row.claimed_at)

    def test_partial_unique_blocks_second_claim_when_pending(self):
        _row(source="signup_reminder", source_id=3, success=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _row(source="signup_reminder", source_id=3, success=None)

    def test_partial_unique_blocks_second_claim_when_successful(self):
        _row(source="signup_reminder", source_id=4, success=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _row(source="signup_reminder", source_id=4, success=None)

    def test_partial_unique_DOES_NOT_block_after_failed_send(self):
        # Failed sends are reclaimable so transient errors don't permanently brick reminders
        _row(source="signup_reminder", source_id=5, success=False)
        # Re-claim should succeed
        _row(source="signup_reminder", source_id=5, success=None)

    def test_unique_is_per_source_and_event(self):
        _row(source="signup_reminder", source_id=6, success=True)
        # Different source_id — fine
        _row(source="signup_reminder", source_id=7, success=True)
        # Different source — fine
        _row(source="attendance_reminder", source_id=6, success=True)
```

- [ ] **Step 3: Run — confirm failure**

```bash
just test::run 'python manage.py test events.tests.test_idempotency -v 2'
```

Expected: FAIL — `success` is non-nullable, no `claimed_at` field, no constraint.

- [ ] **Step 4: Update the model**

Edit `backend/discordbot/models.py` `DiscordMessageLog`:

```python
class DiscordMessageLog(models.Model):
    # ... existing fields (channel_id, embed_data, source, source_id, message_id, etc.) ...
    success = models.BooleanField(null=True, blank=True)  # was non-nullable; NULL = lease held
    claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)  # NEW
    # ... rest unchanged ...

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=models.Q(success__isnull=True) | models.Q(success=True),
                name="uniq_discord_message_log_source_event_when_pending_or_success",
            ),
        ]
```

The `Q(success__isnull=True) | Q(success=True)` predicate is logically equivalent to `success IS NOT FALSE`. Django renders this as a partial index in Postgres.

- [ ] **Step 5: Generate the migration**

```bash
just dev::exec backend python manage.py makemigrations discordbot --name discord_message_log_lease_schema
```

Expected: migration file with three operations — `AlterField` (success nullable), `AddField` (claimed_at), `AddConstraint` (partial unique).

- [ ] **Step 6: Edit the migration for production deploy safety**

Open the new migration file. Set `atomic = False` and use `CREATE UNIQUE INDEX CONCURRENTLY` for the partial index — this avoids blocking writes during deploy:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    dependencies = [
        ("discordbot", "<previous_migration_name>"),
    ]

    operations = [
        migrations.AlterField(
            model_name="discordmessagelog",
            name="success",
            field=models.BooleanField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="discordmessagelog",
            name="claimed_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
                "uniq_discord_message_log_source_event_when_pending_or_success "
                "ON discordbot_discordmessagelog (source, source_id) "
                "WHERE success IS NOT FALSE;"
            ),
            reverse_sql=(
                "DROP INDEX IF EXISTS uniq_discord_message_log_source_event_when_pending_or_success;"
            ),
            state_operations=[
                # Mirror the constraint in Django's model state so tests/ORM see it
                migrations.AddConstraint(
                    model_name="discordmessagelog",
                    constraint=models.UniqueConstraint(
                        fields=["source", "source_id"],
                        condition=models.Q(success__isnull=True) | models.Q(success=True),
                        name="uniq_discord_message_log_source_event_when_pending_or_success",
                    ),
                ),
            ],
        ),
    ]
```

For SQLite (test/dev), `CONCURRENTLY` is silently ignored. The `state_operations` ensures Django ORM enforces the constraint in tests via `IntegrityError`.

- [ ] **Step 7: Pre-flight check for duplicate rows in production data**

Before applying in prod, check no existing rows already violate the new constraint:

```sql
SELECT source, source_id, COUNT(*)
FROM discordbot_discordmessagelog
WHERE success IS NOT FALSE
GROUP BY source, source_id
HAVING COUNT(*) > 1;
```

Expected: zero rows. If non-empty, deduplicate manually before migrating (older successful row wins; delete duplicates).

- [ ] **Step 8: Apply the migration**

```bash
just db::migrate::all
```

- [ ] **Step 9: Run — confirm test passes**

```bash
just test::run 'python manage.py test events.tests.test_idempotency -v 2'
```

Expected: all 6 tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/discordbot/models.py backend/discordbot/migrations/ backend/events/tests/test_idempotency.py
git commit -m "feat(discord): DiscordMessageLog lease schema (Option B)

success is now nullable (NULL = lease held). New claimed_at timestamp
lets the sweeper reclaim crashed-worker leases. Partial unique index
on (source, source_id) WHERE success IS NOT FALSE: blocks duplicate
sends while a pending or successful row exists, but allows retry
after a failed send. The full row (including required channel_id +
embed_data) is supplied by the worker at claim time."
```

### Task 1.2.5: Claim/finalize helpers + internal API endpoints

**Files:**
- Modify: `backend/app/views/internal.py` — split the existing message-log creation endpoint into claim + finalize handlers
- Modify: `backend/app/internal_client.py` — add `claim_discord_message_log` and `finalize_discord_message_log` worker-side helpers
- Modify: `backend/discordbot/utils.py` — split `sync_send_embed_with_components` into `_no_log` (Discord HTTP only) + thin wrapper that adds claim/finalize
- Test: `backend/discordbot/tests/test_lease_helpers.py` (new)

**Why:** The reminder tasks need to acquire the lease BEFORE the Discord send. That requires a worker-callable `claim` step that returns either a log row PK or None (lease held by another worker). After the send, `finalize` updates the row to `success=True/False`. `sync_send_embed_with_components` is currently the worker's only entry point and writes the log row AFTER the send — refactor it so the same public signature now does claim → send → finalize internally.

- [ ] **Step 1: Read the existing internal log endpoint**

```bash
grep -n "create_discord_message_log\|message-log" backend/app/views/internal.py | head -10
```

Expected: a POST handler at `/api/internal/discord/message-log/` that does `DiscordMessageLog.objects.create(**data)`.

- [ ] **Step 2: Write the failing claim + finalize tests**

Create `backend/discordbot/tests/test_lease_helpers.py`:

```python
from django.test import TestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog
from app.internal_client import (
    claim_discord_message_log,
    finalize_discord_message_log,
)


CLAIM_PAYLOAD = dict(channel_id="ch_1", embed_data={"title": "test"})


class LeaseHelpersTest(TestCase):
    def test_claim_returns_log_id(self):
        log_id = claim_discord_message_log(
            source="event_announcement", source_id=10, **CLAIM_PAYLOAD,
        )
        self.assertIsNotNone(log_id)
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertIsNone(row.success)
        self.assertIsNotNone(row.claimed_at)
        self.assertEqual(row.channel_id, "ch_1")
        self.assertEqual(row.embed_data, {"title": "test"})

    def test_claim_returns_none_when_pending_lease_held(self):
        DiscordMessageLog.objects.create(
            source="event_announcement", source_id=11,
            success=None, claimed_at=timezone.now(),
            channel_id="ch_1", embed_data={"title": "prior"},
        )
        result = claim_discord_message_log(
            source="event_announcement", source_id=11, **CLAIM_PAYLOAD,
        )
        self.assertIsNone(result)

    def test_claim_returns_none_when_already_succeeded(self):
        DiscordMessageLog.objects.create(
            source="event_announcement", source_id=12, success=True,
            channel_id="ch_1", embed_data={"title": "prior"},
        )
        result = claim_discord_message_log(
            source="event_announcement", source_id=12, **CLAIM_PAYLOAD,
        )
        self.assertIsNone(result)

    def test_claim_succeeds_after_failed_send(self):
        # Failed sends do NOT block re-claim — partial unique excludes success=False
        DiscordMessageLog.objects.create(
            source="event_announcement", source_id=13, success=False,
            channel_id="ch_1", embed_data={"title": "prior"},
        )
        log_id = claim_discord_message_log(
            source="event_announcement", source_id=13, **CLAIM_PAYLOAD,
        )
        self.assertIsNotNone(log_id)

    def test_finalize_marks_success_true(self):
        log_id = claim_discord_message_log(
            source="event_announcement", source_id=14, **CLAIM_PAYLOAD,
        )
        finalize_discord_message_log(log_id, success=True, message_id="msg_1")
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertTrue(row.success)
        self.assertEqual(row.discord_message_id, "msg_1")

    def test_finalize_marks_success_false(self):
        log_id = claim_discord_message_log(
            source="event_announcement", source_id=15, **CLAIM_PAYLOAD,
        )
        finalize_discord_message_log(log_id, success=False, error="HTTP 500")
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertFalse(row.success)

    def test_finalize_on_swept_row_returns_silently(self):
        # The sweeper may have deleted the row between claim and finalize.
        # finalize must not raise — it's a no-op.
        finalize_discord_message_log(99999, success=True, message_id="msg_1")
        # No assertion needed — should not raise
```

- [ ] **Step 3: Run — confirm failure**

```bash
just test::run 'python manage.py test discordbot.tests.test_lease_helpers -v 2'
```

Expected: FAIL — helpers don't exist.

- [ ] **Step 4: Add the internal API endpoints (using existing auth pattern)**

Edit `backend/app/views/internal.py`. Add two new endpoints AFTER the existing `create_discord_message_log` function. Use the SAME decorator stack (`@api_view`, `@authentication_classes(_auth)`, `@permission_classes(_perm)`) — these endpoints are NOT csrf_exempt; they go through the project's existing internal-service auth:

```python
from django.db import IntegrityError, transaction
from django.utils import timezone


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def claim_discord_message_log_view(request):
    """POST /api/internal/discord/message-log/claim/

    Body: {"source": str, "source_id": int, "channel_id": str, "embed_data": dict,
           "fired_by_user_id": int?, "tournament_log_id": int?}
    Returns: 201 {"id": <pk>} on success, 409 {} on conflict (lease held).
    """
    from discordbot.models import DiscordMessageLog

    err = _validate_required(
        request.data, ["source", "source_id", "channel_id", "embed_data"]
    )
    if err:
        return err

    create_kwargs = {
        "source": request.data["source"],
        "source_id": request.data["source_id"],
        "channel_id": request.data["channel_id"],
        "embed_data": request.data["embed_data"],
        "success": None,
        "claimed_at": timezone.now(),
    }
    if "fired_by_user_id" in request.data:
        create_kwargs["fired_by_id"] = request.data["fired_by_user_id"]
    if "tournament_log_id" in request.data:
        create_kwargs["tournament_log_id"] = request.data["tournament_log_id"]

    try:
        with transaction.atomic():
            row = DiscordMessageLog.objects.create(**create_kwargs)
        return Response({"id": row.pk}, status=status.HTTP_201_CREATED)
    except IntegrityError:
        return Response({}, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def finalize_discord_message_log_view(request, log_id):
    """POST /api/internal/discord/message-log/<log_id>/finalize/

    Body: {"success": bool, "discord_message_id": str?, "error": str?,
           "status_code": int?, "response_data": dict?}
    Returns: 200 on update, 410 Gone if the row was already swept.
    """
    from discordbot.models import DiscordMessageLog

    err = _validate_required(request.data, ["success"])
    if err:
        return err

    update_fields = {"success": request.data["success"]}
    for k in ("discord_message_id", "status_code", "response_data"):
        if k in request.data:
            update_fields[k] = request.data[k]

    updated = DiscordMessageLog.objects.filter(pk=log_id).update(**update_fields)
    if updated == 0:
        # Sweeper got there first, or the log_id was bogus
        return Response(
            {"detail": "log row not found (likely swept)"},
            status=status.HTTP_410_GONE,
        )
    return Response({}, status=status.HTTP_200_OK)
```

Add URL routes alongside the existing `create_discord_message_log` route in the internal API urlconf. Find via `grep -rn 'create_discord_message_log\|message-log' backend/app/urls*.py backend/backend/urls.py`. The pattern matches the existing internal route shape.

- [ ] **Step 5: Add the worker-side helpers**

Edit `backend/app/internal_client.py`. Use whichever `_post` helper the file already follows (it has its own auth-header pattern):

```python
def claim_discord_message_log(
    *, source: str, source_id: int, channel_id: str, embed_data: dict,
    fired_by_user_id: int | None = None, tournament_log_id: int | None = None,
) -> int | None:
    """Acquire a pre-send lease.

    The claim row is fully populated (channel_id + embed_data are required
    DiscordMessageLog fields). Returns the new row's PK on success, or None
    on 409 (lease held by another worker, or row already in pending/success
    state for this source/source_id).
    """
    payload = {
        "source": source,
        "source_id": source_id,
        "channel_id": channel_id,
        "embed_data": embed_data,
    }
    if fired_by_user_id is not None:
        payload["fired_by_user_id"] = fired_by_user_id
    if tournament_log_id is not None:
        payload["tournament_log_id"] = tournament_log_id

    response = _post("/discord/message-log/claim/", json=payload)
    if response.status_code == 409:
        return None
    response.raise_for_status()
    return response.json()["id"]


def finalize_discord_message_log(
    log_id: int,
    *,
    success: bool,
    message_id: str | None = None,
    error: str | None = None,
    status_code: int | None = None,
    response_data: dict | None = None,
) -> None:
    """Update the lease row to its final state. Silently no-ops on 410 Gone
    (sweeper reaped the row before finalize landed)."""
    payload = {"success": success}
    if message_id is not None:
        payload["discord_message_id"] = message_id
    if error is not None:
        # Stash the error string in response_data for visibility
        payload["response_data"] = {"error": error}
    if status_code is not None:
        payload["status_code"] = status_code
    if response_data is not None:
        existing = payload.get("response_data") or {}
        existing.update(response_data)
        payload["response_data"] = existing

    response = _post(f"/discord/message-log/{log_id}/finalize/", json=payload)
    if response.status_code == 410:
        return  # row was swept; nothing to do
    response.raise_for_status()
```

- [ ] **Step 6: Run — confirm test passes**

```bash
just test::run 'python manage.py test discordbot.tests.test_lease_helpers -v 2'
```

Expected: all 7 tests pass.

- [ ] **Step 7: Refactor `sync_send_embed_with_components`**

Edit `backend/discordbot/utils.py`. The existing function calls `_log_discord_message` AFTER the send; refactor so the lease bracketsthe send. Existing wrapper signature stays the same — callers don't need updates.

```python
def sync_send_embed_with_components_no_log(
    *, channel_id, embed, components=None,
):
    """Discord HTTP send only. Caller is responsible for logging."""
    # ... copy the existing send logic from sync_send_embed_with_components,
    # MINUS the _log_discord_message call at the end. Return the Discord
    # API response dict (or whatever the existing function returns). ...


def sync_send_embed_with_components(
    *, channel_id, embed, components=None, source, source_id,
    fired_by_user_id=None, tournament_log_id=None,
):
    """Backward-compatible wrapper. Adds pre-send lease around _no_log.

    Returns:
        - The Discord API response dict on a successful send
        - None if the lease was already held (another worker won the race)
        - None if the lease was held but in a False (failed) state — caller
          will retry on the next poll cycle
    """
    from app.internal_client import claim_discord_message_log, finalize_discord_message_log

    log_id = claim_discord_message_log(
        source=source,
        source_id=source_id,
        channel_id=channel_id,
        embed_data=embed,
        fired_by_user_id=fired_by_user_id,
        tournament_log_id=tournament_log_id,
    )
    if log_id is None:
        return None  # lease held by another worker

    try:
        response = sync_send_embed_with_components_no_log(
            channel_id=channel_id, embed=embed, components=components,
        )
        finalize_discord_message_log(
            log_id,
            success=True,
            message_id=response.get("id") if response else None,
            response_data=response,
        )
        return response
    except Exception as e:
        finalize_discord_message_log(log_id, success=False, error=str(e))
        raise
```

The previous `_log_discord_message` helper at `discordbot/utils.py:110-148` is no longer called from `sync_send_embed_with_components`. Audit other callers via `grep -rn '_log_discord_message' backend/`. If only this function used it, delete it; otherwise leave for non-lease callers.

- [ ] **Step 8: Run the full discord+events test suite**

```bash
just test::run 'python manage.py test discordbot events -v 2'
```

Expected: PASS. Existing reminder-task tests should be unaffected since the public signature of `sync_send_embed_with_components` is unchanged — they just gain implicit lease semantics.

- [ ] **Step 9: Commit**

```bash
git add backend/app/views/internal.py backend/app/internal_client.py backend/app/urls*.py backend/discordbot/utils.py backend/discordbot/tests/test_lease_helpers.py
git commit -m "feat(discord): claim/finalize helpers for pre-send lease

claim_discord_message_log creates a NULL-success row before the send;
unique constraint ensures only one worker reaches the send step.
finalize_discord_message_log marks the row True/False after the send
result is known. sync_send_embed_with_components is refactored to do
this internally; existing callers get the new behavior for free."
```

### Task 1.3: Refactor `send_event_announcement` and `send_subscriber_notifications` for the lease flow

**Files:**
- Modify: `backend/events/tasks.py` — `send_event_announcement` (line ~192), `send_subscriber_notifications` (line ~858)
- Test: `backend/events/tests/test_reminder_lease_flow.py` (new)

**Why:** The existing reminder tasks pass `source` and `source_id` to `sync_send_embed_with_components`, which (after Task 1.2.5) now does claim → send → finalize internally. The reminder tasks themselves need only a small change: handle the `None` return from the wrapper (lease was held) and add `acks_late=True` on the `@shared_task` decorator.

- [ ] **Step 1: Write the failing lease-respect test**

Create `backend/events/tests/test_reminder_lease_flow.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog
from events.tasks import send_event_announcement
from events.tests.factories import EventFactory


class SendEventAnnouncementLeaseTest(TestCase):
    @patch("discordbot.utils.sync_send_embed_with_components_no_log")
    def test_skips_send_when_lease_already_held(self, mock_send_raw):
        event = EventFactory(
            discord_announcement=True, discord_announcement_channel_id="ch_1",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement", source_id=event.pk,
            success=None, claimed_at=timezone.now(),
        )
        result = send_event_announcement(event.pk)
        mock_send_raw.assert_not_called()
        self.assertIn("lease", result.lower())

    @patch("discordbot.utils.sync_send_embed_with_components_no_log")
    def test_sends_when_no_prior_log_exists(self, mock_send_raw):
        mock_send_raw.return_value = {"id": "msg_1"}
        event = EventFactory(
            discord_announcement=True, discord_announcement_channel_id="ch_1",
        )
        send_event_announcement(event.pk)
        mock_send_raw.assert_called_once()
        row = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=event.pk,
        )
        self.assertTrue(row.success)
        self.assertEqual(row.message_id, "msg_1")
```

- [ ] **Step 2: Run — confirm failure**

```bash
just test::run 'python manage.py test events.tests.test_reminder_lease_flow -v 2'
```

Expected: FAIL — current task doesn't handle the None return path.

- [ ] **Step 3: Update `send_event_announcement`**

Edit `backend/events/tasks.py:192`. The change is small — handle the `None` return from `sync_send_embed_with_components` (which now means "lease was already held"):

```python
@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_event_announcement(event_id):
    """..."""
    # ... existing setup: load event, check announcement enabled, build embed ...

    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source="event_announcement",
        source_id=event.pk,
    )
    if response is None:
        return f"Event {event_id} announcement: lease held by another worker"

    return f"Sent announcement for event {event_id}"
```

- [ ] **Step 4: Update `send_subscriber_notifications` to wrap the entire DM loop in a lease**

`send_subscriber_notifications` does NOT use `sync_send_embed_with_components`. It iterates subscribers and sends a DM each via `sync_send_dm` (per-`DiscordEventDM` row), then writes a summary `create_message_log` at the end. The lease pattern needs to be applied at the function bounds — claim BEFORE the loop, finalize AFTER, so concurrent dispatches can't double-DM the entire subscriber set.

Edit `backend/events/tasks.py:858`. Add lease bracketing around the existing loop:

```python
@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_subscriber_notifications(event_id):
    """Send signup reminder DMs to repeater subscribers...

    Wrapped in a lease so concurrent dispatches don't iterate the
    subscriber set twice. The 'embed' payload at claim time is the
    common embed used for each DM (built once below); channel_id
    is N/A for DMs but the field is required, so we use a sentinel.
    """
    from app.internal_client import (
        claim_discord_message_log,
        finalize_discord_message_log,
        get_event_for_task,
        get_repeater_subscribers,
    )
    # ... other existing imports unchanged ...

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.event_repeater_id:
        return "No repeater"

    # Build the DM embed once (used for the lease payload AND each subscriber)
    dm_data = build_subscriber_dm_embed(event)

    # Claim the lease BEFORE iterating subscribers
    log_id = claim_discord_message_log(
        source="signup_reminder",
        source_id=event_id,
        channel_id="dm",  # sentinel — DMs are not per-channel
        embed_data=dm_data["embed"],
    )
    if log_id is None:
        return f"Signup reminder for event {event_id}: lease held by another worker"

    sent = skipped = failed = 0
    try:
        # ... existing subscriber loop body, unchanged ...
        # (build subscriber list, iterate, sync_send_dm per subscriber,
        #  track sent/skipped/failed counters)
        pass
    except Exception as e:
        finalize_discord_message_log(log_id, success=False, error=str(e))
        raise

    finalize_discord_message_log(
        log_id, success=True,
        response_data={"sent": sent, "skipped": skipped, "failed": failed},
    )
    return f"Subscriber DMs for event {event_id}: {sent} sent, {skipped} skipped, {failed} failed"
```

Important: the subscriber loop's *existing* `create_message_log` call at the end of the function is REPLACED by `finalize_discord_message_log` (the lease row is the audit log). Per-subscriber `DiscordEventDM` records are unaffected — they remain a separate per-recipient log.

The `channel_id="dm"` sentinel works because the partial unique index keys on `(source, source_id)` only — `channel_id` doesn't participate in the constraint. Worth a code comment so future maintainers don't get confused.

- [ ] **Step 5: Run — confirm pass**

```bash
just test::run 'python manage.py test events.tests.test_reminder_lease_flow -v 2'
```

Expected: PASS.

- [ ] **Step 6: Run the broader event-task suite**

```bash
just test::run 'python manage.py test events.tests.test_discord_tasks events.tests.test_discord_integration -v 2'
```

Expected: PASS — public signatures of both reminder tasks unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/events/tasks.py backend/events/tests/test_reminder_lease_flow.py
git commit -m "feat(events): reminder tasks respect lease semantics

send_event_announcement uses the lease via sync_send_embed_with_components.
send_subscriber_notifications wraps its subscriber-DM loop in an
explicit claim/finalize pair (it doesn't go through sync_send_embed,
so the wrapper alone wouldn't protect it). acks_late + reject_on_worker_lost
ensure a worker crash leaves a pending lease that the sweeper reaps
within 1 minute."
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

Insert into `backend/events/tasks.py` (just after `send_event_announcement`):

```python
@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_attendance_reminder(event_id):
    """Post the attendance-confirmation embed to the announcement channel.

    Extracted from the inline block formerly in check_event_reminders.
    Idempotency is provided by sync_send_embed_with_components's
    internal claim/finalize lease pattern.
    """
    from app.internal_client import get_event_for_task
    from discordbot.utils import sync_send_embed_with_components
    from events.discord import build_attendance_reminder_embed

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"

    result = build_attendance_reminder_embed(event)
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source="attendance_reminder",
        source_id=event.pk,
    )
    if response is None:
        return f"Attendance reminder for event {event_id}: lease held by another worker"

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

Pulls the inline block out of check_event_reminders. Lease pattern
prevents duplicate sends; acks_late ensures worker crashes do not
drop the task — pending lease will be reaped by the sweeper."
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
@shared_task(acks_late=True, reject_on_worker_lost=True)
def send_profile_reminder(event_id):
    """Post the profile-completion reminder embed to the announcement channel.

    Extracted from the inline block formerly in check_event_reminders.
    Idempotency via the lease pattern in sync_send_embed_with_components.
    """
    from app.internal_client import get_event_for_task
    from discordbot.utils import sync_send_embed_with_components
    from events.discord import build_profile_reminder_embed

    event = get_event_for_task(event_id)
    if not event:
        return f"Event {event_id} not found"
    if not event.discord_announcement_channel_id:
        return f"No channel for event {event_id}"

    result = build_profile_reminder_embed(event)
    response = sync_send_embed_with_components(
        channel_id=event.discord_announcement_channel_id,
        embed=result["embed"],
        components=result.get("components"),
        source="profile_reminder",
        source_id=event.pk,
    )
    if response is None:
        return f"Profile reminder for event {event_id}: lease held by another worker"

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

# Force-import the tasks module so @shared_task registrations populate
# current_app.tasks. Without this, Django's test runner may not have
# imported events.tasks, and the task-name validity assertion below
# would pass vacuously in CI but fail in production.
import events.tasks  # noqa: F401

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
```

(No `reminder_field_union` helper is needed — `DISCORD_CONFIG_FIELDS` in `services.py:536` is already auto-built from `DiscordEventConfigMixin._meta.get_fields()` and catches every reminder field. The CI guardrail in Task 1.10 enforces that registry fields stay on the mixin.)

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

Idempotency: in-process check via DiscordMessageLog is an optimization
(load-shedder); the actual guarantee is the pre-send lease in each
reminder task — the dispatched task tries to INSERT a NULL-success row
before the Discord HTTP send, and the full unique index on
DiscordMessageLog(source, source_id) ensures only one worker wins.
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
    # Patch the SOURCE module of fire_due_reminders, not events.tasks.
    # The new check_event_reminders body does `from events.scheduling.fire
    # import fire_due_reminders` *inside* the function, so the lookup
    # happens at call time against events.scheduling.fire's namespace.
    # Patching events.tasks.fire_due_reminders would not intercept it.
    @patch("events.scheduling.fire.fire_due_reminders")
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
    invalidated on insert). Idempotency is enforced by the pre-send lease
    pattern: each reminder task INSERTs a NULL-success row before the
    Discord HTTP send, and the partial unique index on (source, source_id)
    WHERE success IS NOT FALSE makes the second worker's claim raise
    IntegrityError — preventing duplicate Discord messages, not just
    duplicate audit rows. See sweep_stale_discord_leases for crash recovery.
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

### Task 1.9: Remove immediate `notify_event_announced` dispatch + audit other call sites of `send_event_announcement`

**Files:**
- Modify: `backend/events/views.py` (lines ~376, ~420, ~551 — `notify_event_announced(event)` calls)
- Modify: `backend/events/services.py` (line ~651 — `notify_event_announced(event)` call)
- Test: `backend/events/tests/test_announcement_scheduled.py` (new)

**Why:** With the announcement now in `REMINDERS`, the immediate `.delay()` dispatch on save would race the scheduled fire and could result in either an early send or a wasted scheduled task hitting an existing lease. Remove all four `notify_event_announced(event)` call sites.

**Other call sites of `send_event_announcement` are intentionally preserved.** Two more references exist that we are NOT removing:
- `backend/events/views.py:1184-1185` — TASK_MAP in the admin "fire now" / manual-trigger viewset (lets a site admin manually re-fire an announcement). Manual trigger semantics: admin acknowledges they're forcing a send. The lease pattern protects this — a manual re-fire after a successful send hits the unique constraint and returns "lease held," which is the right behavior. Document this in a code comment.
- `backend/events/tasks.py:150` — likely a synchronous helper or admin entry point. Verify its purpose with `git blame` and a grep of its callers; if it's also a manual-trigger, leave it. If it's another auto-dispatch we missed, remove it.

```bash
grep -rn "send_event_announcement" backend/ --include="*.py" | grep -v migrations
```

Expected after this task: 4 call sites removed (3 in views.py, 1 in services.py); 2 call sites remain (TASK_MAP at views.py:1184-1185, and tasks.py:150 if confirmed manual-trigger).

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

### Task 1.10: `sync_future_events` returns touched events + post-commit invalidation; mixin-coverage CI guardrail

**Files:**
- Modify: `backend/events/services.py:661-691` (`sync_future_events` — change return value, add `invalidate_after_commit`)
- Modify: `backend/events/views.py:190-195` (`EventRepeaterViewSet.perform_update`)
- Test: `backend/events/tests/test_sync_future_events_cascade.py` (new)

**Why:** Reading the actual `sync_future_events` at `services.py:661-691` reveals the cascade is *already* generic — it iterates `DISCORD_CONFIG_FIELDS` (auto-built from `DiscordEventConfigMixin._meta.get_fields()` at line 536-538). Any reminder field defined on the mixin is automatically cascaded. The original spec's "leaky cascade" framing was inaccurate. What the function DOES need:

1. Return the list of touched events (currently returns just a count) so callers can pass them to `invalidate_after_commit`.
2. Skip the redundant inner `with transaction.atomic()` (function is already `@transaction.atomic`-decorated at line 661).
3. Add a CI guardrail asserting every `ScheduledReminder.hours_field` and `enabled_field` is on the `DiscordEventConfigMixin` (extending Task 1.6's registry test) — so a future reminder can't be added outside the mixin and silently miss the cascade.

- [ ] **Step 1: Read the current cascade**

```bash
sed -n '526,545p' backend/events/services.py    # the *_FIELDS constants
sed -n '661,695p' backend/events/services.py    # sync_future_events itself
```

Confirmed: `DISCORD_CONFIG_FIELDS = [f.name for f in DiscordEventConfigMixin._meta.get_fields() if hasattr(f, "column")]` (line 536). The cascade already covers every field on the mixin.

- [ ] **Step 2: Write the failing cascade-coverage test**

Create `backend/events/tests/test_sync_future_events_cascade.py`:

```python
from django.test import TestCase
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

The function is *already* `@transaction.atomic`-decorated at the function level (`services.py:661`). Do not add a second `with transaction.atomic()` inside. Use `invalidate_after_commit` from `app.cache_utils`, NOT raw `invalidate_obj` — project convention reserves `invalidate_obj` for M2M paths.

The existing function body uses `_copy_mixin_fields` plus three `*_FIELDS` constants. Keep that structure exactly; only change the return value and add the post-commit invalidation. Replace the body with:

```python
@transaction.atomic
def sync_future_events(repeater):
    """Propagate repeater changes to all upcoming events in the series.

    Only updates events still in EventState.UPCOMING (i.e. signups
    haven't opened yet), so in-progress events are untouched.

    Returns the list of touched Event instances so callers can chain
    a single invalidate_after_commit at the end of the request.
    """
    from app.cache_utils import invalidate_after_commit

    future_events = list(
        Event.objects.filter(
            event_repeater=repeater,
            state=EventState.UPCOMING,
        )
        .select_related("tournament")
        .select_for_update()
    )
    shared_fields = ["name", "description"]
    update_fields = (
        shared_fields
        + TOURNAMENT_TEMPLATE_FIELDS
        + EVENT_CONFIG_FIELDS
        + DISCORD_CONFIG_FIELDS
    )
    for event in future_events:
        for field_name in shared_fields:
            setattr(event, field_name, getattr(repeater, field_name))
        _copy_mixin_fields(repeater, event, TOURNAMENT_TEMPLATE_FIELDS)
        _copy_mixin_fields(repeater, event, EVENT_CONFIG_FIELDS)
        _copy_mixin_fields(repeater, event, DISCORD_CONFIG_FIELDS)
        event.tournament_date = event.scheduled_at
        event.save(update_fields=update_fields + ["tournament_date", "updated_at"])
        sync_tournament_from_event(event)

    # Single batched invalidation post-commit. Outside the loop so
    # all rows are committed before invalidation hooks fire.
    if future_events:
        invalidate_after_commit(*future_events)

    logger.info("Synced %d upcoming events for repeater %s", len(future_events), repeater.pk)
    return future_events  # CHANGED: was `updated` (an int)
```

This matches the existing function structure verbatim except: (1) `select_for_update()` added; (2) explicit `list(...)` so iteration completes before the cacheops post-commit hooks try to evaluate the queryset again; (3) `invalidate_after_commit(*future_events)` post-loop; (4) returns the list instead of an int. Callers that previously used the return value as a count (if any — search via `grep -rn 'sync_future_events' backend/`) get `len(future_events)` instead.

- [ ] **Step 4.5: Extend the registry CI guardrail to assert mixin coverage**

Append to `backend/events/tests/test_scheduling_registry.py`:

```python
class RegistryMixinCoverageTest(TestCase):
    """Ensure every reminder field is on DiscordEventConfigMixin so the
    existing sync_future_events cascade catches it."""

    def test_every_reminder_field_is_on_discord_event_config_mixin(self):
        from events.mixins import DiscordEventConfigMixin  # adapt import path
        mixin_field_names = {
            f.name for f in DiscordEventConfigMixin._meta.get_fields()
            if hasattr(f, "name")
        }
        for r in REMINDERS:
            self.assertIn(
                r.hours_field, mixin_field_names,
                f"Reminder {r.key!r} hours_field {r.hours_field!r} not on "
                f"DiscordEventConfigMixin — sync_future_events cascade would "
                f"silently miss it."
            )
            self.assertIn(
                r.enabled_field, mixin_field_names,
                f"Reminder {r.key!r} enabled_field {r.enabled_field!r} not "
                f"on DiscordEventConfigMixin."
            )
```

Run via `just test::run 'python manage.py test events.tests.test_scheduling_registry.RegistryMixinCoverageTest -v 2'`. Expected: PASS — all four reminder fields are already on the mixin.

- [ ] **Step 5: Update `EventRepeaterViewSet.perform_update` to consume the return**

Edit `backend/events/views.py:190-195`. The existing code already calls `invalidate_after_commit(repeater)` for the repeater itself (per project convention). Add the cascaded events:

```python
def perform_update(self, serializer):
    repeater = serializer.save()
    future_events = sync_future_events(repeater)
    invalidate_after_commit(repeater, *future_events)
```

(The single batched call — repeater + every cascaded event — is more efficient than per-event calls and matches the project's convention.)

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

### Task 1.12: Verify existing `EventViewSet.perform_update` invalidation is sufficient

**Files:**
- Modify: nothing — this task is verification only
- Test: `backend/events/tests/test_event_edit_invalidates_cache.py` (new — verifies existing behavior)

**Why:** `EventViewSet.perform_update` (`views.py:380-383`) already calls `invalidate_after_commit(event)` per the project's existing convention. The spec's requirement is met by existing code. This task adds a regression test asserting the invalidation happens, so future refactors don't accidentally remove it. (The plan originally proposed adding raw `invalidate_obj` here, but the second-pass review showed that would duplicate existing `invalidate_after_commit` and mix conventions — drop that plan.)

- [ ] **Step 1: Read the existing invalidation in `EventViewSet.perform_update`**

```bash
sed -n '370,425p' backend/events/views.py
```

Expected: `invalidate_after_commit(event)` is called after `serializer.save()`. Confirm the import comes from `app.cache_utils`.

- [ ] **Step 2: Write the regression test**

Create `backend/events/tests/test_event_edit_invalidates_cache.py`:

```python
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from events.tests.factories import EventFactory


class EventEditInvalidatesCacheTest(TestCase):
    @patch("events.views.invalidate_after_commit")
    def test_perform_update_invalidates_event(self, mock_invalidate):
        event = EventFactory()
        client = APIClient()
        client.force_authenticate(user=event.organization.owner)
        client.patch(f"/api/events/{event.pk}/", {"name": "Edited"})

        # Existing behavior: at minimum, invalidate_after_commit is called
        # with the saved event (and possibly more — repeater, future events).
        called_with_event = any(
            event in call.args
            for call in mock_invalidate.call_args_list
        )
        self.assertTrue(called_with_event)
```

- [ ] **Step 3: Run the test**

```bash
just test::run 'python manage.py test events.tests.test_event_edit_invalidates_cache -v 2'
```

Expected: PASS — the existing implementation already calls `invalidate_after_commit(event)`.

- [ ] **Step 4: Commit**

```bash
git add backend/events/tests/test_event_edit_invalidates_cache.py
git commit -m "test(events): regression — perform_update invalidates event cache

Locks in the existing invalidate_after_commit(event) call so refactors
do not silently remove it. No production code changes — the spec
requirement was already satisfied."
```

### Task 1.13: Concurrency test — lease pattern prevents duplicate sends

**Files:**
- Test: `backend/events/tests/test_idempotency.py` (extend)

**Why:** End-to-end verification that the lease pattern prevents duplicate Discord HTTP sends, not just duplicate audit log rows. The relevant race is **between two dispatched reminder tasks running in parallel** — both must call `claim_discord_message_log`, and only one should reach the actual Discord send.

- [ ] **Step 1: Write the concurrent-task test**

Append to `backend/events/tests/test_idempotency.py`:

```python
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.test import TransactionTestCase
from discordbot.models import DiscordMessageLog
from events.tasks import send_event_announcement
from events.tests.factories import EventFactory


class ConcurrentReminderTasksProduceOneSendTest(TransactionTestCase):
    @patch("discordbot.utils.sync_send_embed_with_components_no_log")
    def test_parallel_reminder_tasks_send_to_discord_exactly_once(
        self, mock_send_raw
    ):
        # Mock returns a fake Discord response. We assert it's called
        # AT MOST ONCE no matter how many concurrent tasks fire.
        mock_send_raw.return_value = {"id": "msg_real"}
        event = EventFactory(
            discord_announcement=True,
            discord_announcement_channel_id="ch_1",
        )

        # Two parallel invocations of the SAME reminder task — simulates
        # what happens if check_event_reminders dispatches twice in
        # quick succession (e.g., overlap from a hung worker).
        with ThreadPoolExecutor(max_workers=2) as exe:
            futures = [
                exe.submit(send_event_announcement, event.pk)
                for _ in range(2)
            ]
            results = [f.result() for f in futures]

        # The Discord HTTP send happened at most once — the lease pattern
        # prevents duplicate sends, not just duplicate log rows.
        self.assertEqual(mock_send_raw.call_count, 1)

        # Exactly one final DiscordMessageLog row exists, with success=True.
        success_rows = DiscordMessageLog.objects.filter(
            source="event_announcement", source_id=event.pk, success=True,
        )
        self.assertEqual(success_rows.count(), 1)

        # The "lost-the-race" task returned a "lease held" message.
        race_loser_messages = [r for r in results if "lease" in r.lower()]
        self.assertEqual(len(race_loser_messages), 1)
```

- [ ] **Step 2: Run the test**

```bash
just test::run 'python manage.py test events.tests.test_idempotency.ConcurrentReminderTasksProduceOneSendTest -v 2'
```

Expected: PASS — only one Discord send, only one final success row, one task reports "lease held."

- [ ] **Step 3: Commit**

```bash
git add backend/events/tests/test_idempotency.py
git commit -m "test(events): concurrent reminder tasks send to Discord exactly once

End-to-end verification of the lease pattern: two parallel
send_event_announcement invocations result in exactly one Discord
HTTP send and one success row. The lost-the-race task short-circuits
with 'lease held' and never calls Discord."
```

### Task 1.13.5: Stale-lease sweeper (handles both pending and aged-out failures)

**Files:**
- Modify: `backend/discordbot/tasks.py` (file already exists per `grep` of the repo — adds `sweep_stale_discord_leases` alongside the existing tasks)
- Modify: `backend/config/celery.py` — add to `_beat_schedule` at 60-second cadence
- Test: `backend/discordbot/tests/test_sweep_stale_leases.py` (new)

**Why:** Two recovery cases:

1. **Pending leases (`success=NULL`) older than 5 minutes** — almost always from a worker crash between claim and finalize. Without recovery, the partial unique constraint blocks all future fires for that (source, source_id).
2. **Failed leases (`success=False`) older than 1 hour** — Discord transient 5xx, rate-limit, or temporary auth issue. The next reminder poll's threshold check is the right re-fire trigger; aging out the failure row lets the partial unique index allow the re-claim. 1 hour is the retry budget — long enough that admins can investigate the failure log first; short enough to limit user-visible impact.

The 60-second cadence (vs 5 minutes) keeps total recovery latency to < ~1.5 min for crashed workers.

- [ ] **Step 1: Write the failing sweeper test**

Create `backend/discordbot/tests/test_sweep_stale_leases.py`:

```python
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from discordbot.models import DiscordMessageLog
from discordbot.tasks import sweep_stale_discord_leases


def _row(**overrides):
    defaults = dict(
        channel_id="ch_1",
        embed_data={"title": "test"},
    )
    defaults.update(overrides)
    return DiscordMessageLog.objects.create(**defaults)


class SweepStaleLeasesTest(TestCase):
    def test_deletes_pending_lease_older_than_5_min(self):
        _row(source="event_announcement", source_id=1, success=None,
             claimed_at=timezone.now() - timedelta(minutes=10))
        deleted = sweep_stale_discord_leases()
        self.assertEqual(deleted, 1)
        self.assertFalse(DiscordMessageLog.objects.filter(source_id=1).exists())

    def test_does_not_delete_recent_pending_lease(self):
        _row(source="event_announcement", source_id=2, success=None,
             claimed_at=timezone.now() - timedelta(minutes=2))
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=2).exists())

    def test_does_not_delete_recent_failed_row(self):
        # Recent failures (within the 1-hour budget) stay so admins can investigate
        _row(source="event_announcement", source_id=3, success=False,
             claimed_at=timezone.now() - timedelta(minutes=30))
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=3).exists())

    def test_deletes_aged_out_failed_row(self):
        # Failures older than 1 hour are reaped so the next poll can retry
        _row(source="event_announcement", source_id=4, success=False,
             claimed_at=timezone.now() - timedelta(hours=2))
        deleted = sweep_stale_discord_leases()
        self.assertEqual(deleted, 1)
        self.assertFalse(DiscordMessageLog.objects.filter(source_id=4).exists())

    def test_does_not_delete_successful_rows(self):
        _row(source="event_announcement", source_id=5, success=True,
             claimed_at=timezone.now() - timedelta(days=30))
        sweep_stale_discord_leases()
        self.assertTrue(DiscordMessageLog.objects.filter(source_id=5).exists())
```

- [ ] **Step 2: Run — confirm failure**

```bash
just test::run 'python manage.py test discordbot.tests.test_sweep_stale_leases -v 2'
```

Expected: FAIL — task doesn't exist.

- [ ] **Step 3: Add the sweeper task**

Edit `backend/discordbot/tasks.py` (file already exists; append):

```python
@shared_task
def sweep_stale_discord_leases():
    """Two recoveries:

    - NULL pending leases >5 min old: worker crashed between claim and
      finalize. Delete so the next poll can re-claim.
    - False failed rows >1 hour old: transient Discord error has likely
      passed. Delete so the next poll can retry. Admins should investigate
      via the original failed log row before it ages out.
    """
    from datetime import timedelta
    from django.utils import timezone

    now = timezone.now()
    pending_threshold = now - timedelta(minutes=5)
    failed_threshold = now - timedelta(hours=1)

    pending_swept, _ = DiscordMessageLog.objects.filter(
        success__isnull=True, claimed_at__lt=pending_threshold,
    ).delete()
    failed_swept, _ = DiscordMessageLog.objects.filter(
        success=False, claimed_at__lt=failed_threshold,
    ).delete()

    total = pending_swept + failed_swept
    if total:
        logger.warning(
            "Swept %d stale leases, %d aged-out failures",
            pending_swept, failed_swept,
        )
    return total
```

- [ ] **Step 4: Add to beat schedule**

Edit `backend/config/celery.py` `_beat_schedule`:

```python
"sweep-stale-discord-leases": {
    "task": "discordbot.tasks.sweep_stale_discord_leases",
    "schedule": 60.0,  # every 60 seconds — keeps worker-crash recovery <1.5 min
},
```

- [ ] **Step 5: Run the tests — confirm pass**

```bash
just test::run 'python manage.py test discordbot.tests.test_sweep_stale_leases -v 2'
```

Expected: PASS (all 5 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/discordbot/tasks.py backend/config/celery.py backend/discordbot/tests/test_sweep_stale_leases.py
git commit -m "feat(discord): stale-lease sweeper task (60s cadence)

Reaps DiscordMessageLog rows stuck with success=NULL for >5 minutes,
caused by worker crashes between claim and finalize. Without this,
the unique constraint would permanently block re-fires for the
affected (source, source_id) pair."
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
3. Confirm broker `visibility_timeout` is sufficient for the longest expected reminder task duration. Default Redis is 1 hour; this is fine. Add explicit `broker_transport_options = {'visibility_timeout': 3600}` to `config/celery.py` if not already set.
4. Run pre-flight check for events that will see announcement timing change:
   ```sql
   SELECT id, discord_announcement_hours, scheduled_at
   FROM events_event
   WHERE discord_announcement_hours <> 24
     AND state IN ('upcoming', 'signups_open');
   ```
   Any rows with non-default values will see announcement timing change post-deploy. Notify those event owners if relevant.

**Deploy ordering (matters):**

1. **Run migrations FIRST**: `just db::migrate::prod`. This creates the unique index (`CONCURRENTLY`, no write lock), makes `success` nullable, and adds `claimed_at`. Drops `discord_subscriber_dm*` columns. Safe under writes.
2. **Run cacheops invalidation IMMEDIATELY** before any worker reads cached pre-migration instances:
   ```python
   from cacheops import invalidate_model
   from events.models import Event, EventRepeater
   invalidate_model(Event)
   invalidate_model(EventRepeater)
   ```
   This MUST run before workers restart, not after — workers reading cached pre-migration `Event` instances would crash on dropped-field access.
3. **Roll workers across the full fleet** to the new code. Until all workers are updated, beat is still on the old schedule (no changes); the existing inline reminder branches remain in `check_event_reminders` and continue to work.
4. **Restart celery beat last.** Beat's own config in `config/celery.py` is updated atomically with worker code, but the new task-name dispatches (`send_attendance_reminder`, `send_profile_reminder`) only succeed once all workers have those tasks registered. With `task_acks_late=True` on the polling task, queued reminder tasks sit in Redis until *some* worker picks them up — so the rolling window is bridged automatically as long as broker `visibility_timeout` exceeds the rolling-deploy duration (typically <10 min).

**Post-deploy:**

1. Verify fire path is healthy: tail celery worker logs for ~2 minutes; expect `Checked 4 reminder types` from `fire_due_reminders` every 30s with no errors.
2. Verify the sweeper is registered: `celery -A config inspect scheduled` should list `sweep_stale_discord_leases` at 5-minute cadence.
3. Spot-check a recent reminder fire: `SELECT * FROM discordbot_discordmessagelog ORDER BY id DESC LIMIT 5;` — recent rows should have `success=True` (or `False` for failed Discord calls). Any persistent rows with `success IS NULL` older than 5 minutes mean the sweeper isn't running.

**Rollback:** PR-1 is partially reversible. The schema changes (nullable success, claimed_at, unique index) are forward-only and survive a code rollback without data loss. Restoring pre-PR-1 code re-introduces the inline reminder branches in `check_event_reminders` and the immediate `notify_event_announced` dispatch. Any pending leases from in-flight tasks become unreachable until the sweeper would run (still does as long as the rollback keeps the sweeper task) — manual cleanup of `WHERE success IS NULL` rows is the recovery if rollback is taken without the sweeper.
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
- Pre-send lease pattern on `DiscordMessageLog` (full unique index, nullable `success`, `claimed_at`, 5-min sweeper) prevents duplicate Discord HTTP sends under concurrent races
- `discord_subscriber_dm{,_hours}` dropped (dead fields)
- `discord_announcement_hours` now actually fires the announcement (was inert; behavior change — see deploy notes)
- `sync_future_events` cascades reminder fields generically and uses `invalidate_after_commit` for cacheops
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

### Task 2.1: Realign UPCOMING occurrences after schedule edits (delete-and-regenerate via `_get_next_occurrences`)

**Files:**
- Modify: `backend/events/services.py:661-691` (`sync_future_events` — add schedule-input detection + realignment branch)
- Test: `backend/events/tests/test_sync_future_events_recompute.py` (new)

**Why:** When a repeater's `day_of_week`/`time_of_day`/`timezone`/`starts_at`/`frequency` is edited, existing UPCOMING Event rows keep their stale `scheduled_at`. The hourly `generate_upcoming_events` task (which uses `_get_next_occurrences` at `services.py:551`) then creates new rows at the new schedule — admins see duplicates. The fix: when a schedule input changes, REGENERATE the upcoming-occurrence set via the same `_get_next_occurrences` helper. Delete-and-regenerate is cleaner than per-row recompute because the new schedule may have a different occurrence count (DAILY → WEEKLY changes the count).

**Approach:**

1. Detect "schedule input changed" by capturing the repeater's pre-save schedule values in `EventRepeaterViewSet.perform_update` and passing them through.
2. If unchanged → existing field-cascade behavior (Task 1.10).
3. If changed → delete UPCOMING rows whose `scheduled_at` is NOT in the new occurrence set; insert new occurrences from the new set that don't already exist. Subsequent `generate_upcoming_events` calls become no-ops because the rows are now aligned.

- [ ] **Step 1: Capture pre-save schedule values in the viewset**

Edit `backend/events/views.py` `EventRepeaterViewSet.perform_update` (line ~190). Before `serializer.save()`, snapshot the schedule fields off `serializer.instance`:

```python
SCHEDULE_FIELDS = ("day_of_week", "time_of_day", "timezone", "starts_at", "frequency")

def perform_update(self, serializer):
    pre_save_schedule = {
        f: getattr(serializer.instance, f) for f in SCHEDULE_FIELDS
    }
    repeater = serializer.save()
    schedule_changed = any(
        pre_save_schedule[f] != getattr(repeater, f) for f in SCHEDULE_FIELDS
    )
    future_events = sync_future_events(repeater, realign_schedule=schedule_changed)
    invalidate_after_commit(repeater, *future_events)
```

- [ ] **Step 2: Write the failing realignment test**

Create `backend/events/tests/test_sync_future_events_recompute.py`:

```python
from datetime import datetime, time, timezone as dt_tz
from django.test import TestCase
from events.models import Event
from events.services import sync_future_events
from events.tests.factories import EventFactory, EventRepeaterFactory


class SyncFutureEventsRealignTest(TestCase):
    def test_day_of_week_change_realigns_upcoming_occurrences(self):
        repeater = EventRepeaterFactory(
            day_of_week=1,  # Monday (Sunday=0 convention)
            time_of_day=time(20, 0),
            timezone="UTC",
            generate_days_ahead=14,
        )
        # Pre-populate with a stale Monday occurrence
        stale_event = EventFactory(
            event_repeater=repeater, state="upcoming",
            scheduled_at=datetime(2026, 5, 4, 20, 0, tzinfo=dt_tz.utc),  # Monday
        )

        # Edit repeater to Tuesday
        repeater.day_of_week = 2
        repeater.save()

        sync_future_events(repeater, realign_schedule=True)

        # The stale Monday row is gone
        self.assertFalse(Event.objects.filter(pk=stale_event.pk).exists())
        # New Tuesday occurrences exist
        new_count = Event.objects.filter(
            event_repeater=repeater, state="upcoming",
        ).count()
        self.assertGreater(new_count, 0)
        # All on Tuesdays (Python weekday=1)
        for ev in Event.objects.filter(event_repeater=repeater, state="upcoming"):
            self.assertEqual(ev.scheduled_at.weekday(), 1)

    def test_no_realignment_when_schedule_unchanged(self):
        """When realign_schedule=False, existing scheduled_at values are preserved."""
        repeater = EventRepeaterFactory(day_of_week=1, time_of_day=time(20, 0))
        original_at = datetime(2026, 5, 4, 20, 0, tzinfo=dt_tz.utc)
        event = EventFactory(
            event_repeater=repeater, state="upcoming",
            scheduled_at=original_at,
        )
        sync_future_events(repeater, realign_schedule=False)
        event.refresh_from_db()
        self.assertEqual(event.scheduled_at, original_at)
```

- [ ] **Step 3: Run — confirm failure**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_recompute -v 2'
```

Expected: FAIL — `realign_schedule` parameter doesn't exist; no realignment logic.

- [ ] **Step 4: Add the `realign_schedule` branch to `sync_future_events`**

Edit `backend/events/services.py:661`. Reuse the existing `_get_next_occurrences` helper (already at line 551) plus `generate_events_for_repeater` (already at line 617) — no new helper to write. Add a `realign_schedule` keyword parameter:

```python
@transaction.atomic
def sync_future_events(repeater, *, realign_schedule=False):
    """Propagate repeater changes to all upcoming events in the series.

    If realign_schedule=True (caller detected a day_of_week / time_of_day /
    timezone / starts_at / frequency change), delete UPCOMING rows whose
    scheduled_at no longer matches the repeater's new occurrence set, then
    generate any missing occurrences. This eliminates the "stale Mondays
    plus new Tuesdays" duplicate problem.

    Returns the list of touched Event instances.
    """
    from app.cache_utils import invalidate_after_commit

    if realign_schedule:
        # Same helper that generate_events_for_repeater uses — guarantees
        # timestamp equality between regenerated and pre-existing rows.
        today = _today()
        to_date = today + timedelta(days=repeater.generate_days_ahead)
        new_occurrences = set(_get_next_occurrences(repeater, today, to_date))

        # Delete UPCOMING rows that don't match the new occurrence set
        Event.objects.filter(
            event_repeater=repeater, state=EventState.UPCOMING,
        ).exclude(scheduled_at__in=new_occurrences).delete()

        # Generate missing occurrences (existing helper handles the
        # "row already exists" check via Event.objects.filter(...).exists())
        generate_events_for_repeater(repeater)

    # Cascade field updates onto the (possibly realigned) UPCOMING rowset
    future_events = list(
        Event.objects.filter(
            event_repeater=repeater, state=EventState.UPCOMING,
        )
        .select_related("tournament")
        .select_for_update()
    )
    shared_fields = ["name", "description"]
    update_fields = (
        shared_fields
        + TOURNAMENT_TEMPLATE_FIELDS
        + EVENT_CONFIG_FIELDS
        + DISCORD_CONFIG_FIELDS
    )
    for event in future_events:
        for field_name in shared_fields:
            setattr(event, field_name, getattr(repeater, field_name))
        _copy_mixin_fields(repeater, event, TOURNAMENT_TEMPLATE_FIELDS)
        _copy_mixin_fields(repeater, event, EVENT_CONFIG_FIELDS)
        _copy_mixin_fields(repeater, event, DISCORD_CONFIG_FIELDS)
        event.tournament_date = event.scheduled_at
        event.save(update_fields=update_fields + ["tournament_date", "updated_at"])
        sync_tournament_from_event(event)

    if future_events:
        invalidate_after_commit(*future_events)

    logger.info(
        "Synced %d upcoming events for repeater %s (realign=%s)",
        len(future_events), repeater.pk, realign_schedule,
    )
    return future_events
```

The existing unique constraint on `(event_repeater, scheduled_at)` (already enforced via `generate_events_for_repeater`'s pre-insert check at line 630) prevents duplicates within the regeneration step.

- [ ] **Step 5: Update other callers of `sync_future_events`**

The function gained a keyword-only parameter. Existing callers that pass no value get `False` (no behavior change). Confirm via:

```bash
grep -rn "sync_future_events(" backend/ --include="*.py"
```

The viewset (Step 1) is the primary caller. Any others (e.g. signal handlers) likely don't change schedule and can keep the default.

- [ ] **Step 6: Run the tests — confirm they pass**

```bash
just test::run 'python manage.py test events.tests.test_sync_future_events_recompute -v 2'
```

Expected: PASS.

- [ ] **Step 7: Run broader event tests for regressions**

```bash
just test::run 'python manage.py test events.tests -v 2'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/events/services.py backend/events/views.py backend/events/tests/test_sync_future_events_recompute.py
git commit -m "feat(events): sync_future_events realigns occurrences on schedule edit

When repeater day_of_week/time_of_day/timezone/starts_at/frequency
changes, EventRepeaterViewSet detects the diff and passes
realign_schedule=True. sync_future_events deletes UPCOMING rows whose
scheduled_at is no longer in the repeater's occurrence set, then
generate_events_for_repeater fills any gaps. Eliminates duplicate
occurrences after schedule edits via the same _get_next_occurrences
helper that generates new occurrences in the first place."
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

- [ ] **Step 5: Fix `EditEventModal.tsx:422` — `isRepeater` is hardcoded `false`**

The component already accepts an `isRepeater` prop, but `EditEventModal.tsx:422` passes `false` unconditionally:

```bash
grep -n "isRepeater=" frontend/app/components/events/EditEventModal.tsx
```

Expected output: `isRepeater={false}`. This means the gated block from Step 4 will be hidden even when editing an event that IS part of a repeater (legitimate signup-reminder UX). Replace with the actual condition:

```tsx
// before
isRepeater={false}

// after
isRepeater={event?.event_repeater != null}
```

(`CreateEventModal.tsx` likely has the same pattern with whatever boolean drives "is this a repeater?" — check and align.)

- [ ] **Step 6: Run the test — confirm it passes**

```bash
just test::pw::spec 16-events/05
```

Expected: PASS — fields hidden when the event has no repeater, visible when it does.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/events/DiscordConfigSection.tsx frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx frontend/tests/playwright/e2e/16-events/05-event-form-validation.spec.ts
git commit -m "feat(events): conditionally render signup-reminder fields on event forms

Gate signup_reminder + signup_reminder_hours UI on isRepeater. Fix
EditEventModal's hardcoded isRepeater={false} so repeater-occurrence
events show the fields correctly."
```

### Task 2.4: Zod cross-field rule for single-vs-repeater event schemas (`superRefine`)

**Files:**
- Modify: `frontend/app/components/events/schemas.ts` (lines ~246-247 and surrounding)
- Test: `frontend/app/components/events/__tests__/schemas-discriminated.test.ts` (new — co-located so vitest picks it up; do NOT use `frontend/tests/unit/`)

**Why:** The Zod schema must reject single events that try to set `discord_signup_reminder=true` (no subscribers exist) and accept single events that omit those fields. The plan originally proposed a discriminated union, but the API payload has only `event_repeater: number | null` — no synthetic `event_repeater_kind` field exists. `superRefine` adds a cross-field validation rule on the existing flat object shape with no API change.

- [ ] **Step 1: Confirm vitest config + path alias**

```bash
cat frontend/vitest.config.ts | grep -E 'include|test'
cat frontend/tsconfig.json | grep -A3 '"paths"'
```

Expected: include glob is `app/**/*.test.ts`, alias is `~/`. Test file path below uses both correctly.

- [ ] **Step 2: Write the failing parse tests**

Create `frontend/app/components/events/__tests__/schemas-discriminated.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { eventSchema } from '~/components/events/schemas'

// Helper — minimal valid event payload. Adapt to whatever the existing
// fixture-shape is; copy from an existing test if one exists.
const baseEvent = (overrides = {}) => ({
  id: 1,
  name: 'Test Event',
  scheduled_at: '2026-12-01T20:00:00Z',
  state: 'upcoming',
  organization: 1,
  // ... other required scalar fields from eventSchema ...
  discord_announcement: false,
  discord_announcement_channel_id: null,
  discord_announcement_hours: 24,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_post_signups: false,
  discord_notify_new_events: false,
  ...overrides,
})

describe('event schema — single-vs-repeater rule', () => {
  it('parses a single event without discord_signup_reminder fields', () => {
    const single = baseEvent({ event_repeater: null })
    expect(() => eventSchema.parse(single)).not.toThrow()
  })

  it('rejects a single event with discord_signup_reminder=true', () => {
    const bad = baseEvent({
      event_repeater: null,
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
    })
    expect(() => eventSchema.parse(bad)).toThrow(/signup reminder.*repeater/i)
  })

  it('accepts a single event with discord_signup_reminder=false', () => {
    const ok = baseEvent({
      event_repeater: null,
      discord_signup_reminder: false,
    })
    expect(() => eventSchema.parse(ok)).not.toThrow()
  })

  it('parses a repeater event with discord_signup_reminder fields', () => {
    const r = baseEvent({
      event_repeater: 1,
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
    })
    expect(() => eventSchema.parse(r)).not.toThrow()
  })
})
```

- [ ] **Step 3: Run — confirm failure**

```bash
cd frontend && npx vitest run app/components/events/__tests__/schemas-discriminated.test.ts
```

Expected: FAIL — current schema accepts `event_repeater=null + discord_signup_reminder=true`.

- [ ] **Step 4: Add `superRefine` to the schema**

Edit `frontend/app/components/events/schemas.ts`. After the existing `eventSchema = z.object({...})` definition, chain a refinement:

```typescript
export const eventSchema = z.object({
  // ... existing fields, with discord_signup_reminder*
  //     already optional from PR-0 if needed ...
}).superRefine((val, ctx) => {
  if (val.event_repeater === null && val.discord_signup_reminder === true) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['discord_signup_reminder'],
      message: 'Signup reminder DMs require a recurring event repeater — single events have no subscribers.',
    })
  }
})
```

The same pattern can be applied to any sub-schema (`discordConfigSchema`) that is parsed in isolation against a single-event context. If the form uses one or the other depending on context, refine both.

- [ ] **Step 5: Run — confirm pass**

```bash
cd frontend && npx vitest run app/components/events/__tests__/schemas-discriminated.test.ts
```

Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/events/schemas.ts frontend/app/components/events/__tests__/schemas-discriminated.test.ts
git commit -m "feat(events): superRefine — reject signup_reminder on single events

Cross-field validation rule on the existing flat object shape. No
synthetic discriminator field needed; the rule is API-payload-faithful."
```

### Task 2.5: Conditionally include `discord_signup_reminder*` in modal defaults

**Files:**
- Modify: `frontend/app/components/events/EditEventModal.tsx`, `CreateEventModal.tsx`

**Why:** PR-0 already removed `discord_subscriber_dm*` from all four modals (Task 0.1 step 8). What remains for PR-2 is the *conditional* inclusion of `discord_signup_reminder*` — only on repeater paths. The two repeater-only modals (`EditOrgDefaultsModal`, `EditRepeaterModal`) already have these fields unconditionally and need no change. The two event modals need a conditional spread.

- [ ] **Step 1: Audit the current state**

```bash
grep -n "discord_signup_reminder" frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx
```

Expected: each file references the field unconditionally in `defaultValues` and/or the `reset()` call.

- [ ] **Step 2: For `EditEventModal.tsx`, conditionally include the fields**

In the `defaultValues` object (and the `reset()` call inside `useEffect` if present), wrap the two lines:

```typescript
const defaultValues = {
  // ... other fields ...
  ...(event.event_repeater ? {
    discord_signup_reminder: event.discord_signup_reminder ?? false,
    discord_signup_reminder_hours: event.discord_signup_reminder_hours ?? 24,
  } : {}),
}
```

- [ ] **Step 3: Apply the same pattern to `CreateEventModal.tsx`**

(In Create, the equivalent of `event.event_repeater` is whatever state controls "is this a repeater?" — typically a `eventType === 'repeater'` boolean or similar. Use the project's existing convention.)

- [ ] **Step 4: Run typecheck + Playwright**

```bash
cd frontend && npx tsc --noEmit
just test::pw::spec event
```

Expected: zero TS errors, all event Playwright specs pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/events/EditEventModal.tsx frontend/app/components/events/CreateEventModal.tsx
git commit -m "feat(events): conditional discord_signup_reminder defaults on event modals

Only included when the event is part of a repeater. Combined with the
schemas.ts superRefine in Task 2.4, single events cannot accidentally
set signup_reminder=true."
```

### Task 2.6: Close the TanStack Query invalidation gap

**Files:**
- Modify: `frontend/app/hooks/useEvent.ts` — `useUpdateEventMutation` (correct path; the original plan listed the wrong directory)
- Test: extend a Playwright spec or write a small RTL test

**Why:** Without invalidating `event-discord` and `event-task-schedule` keys, the UI's reminder timing display (15s polled) shows stale values until the next poll.

- [ ] **Step 1: Identify current invalidation logic**

```bash
sed -n '180,200p' frontend/app/hooks/useEvent.ts
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

In `frontend/app/hooks/useEvent.ts`, extend `useUpdateEventMutation`. Use the closure-scoped `eventId` (not `variables.id`) — that's the existing pattern in the file:

```typescript
const queryClient = useQueryClient()
return useMutation({
  // ...
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['events'] })
    queryClient.setQueryData(['event', eventId], data)
    queryClient.invalidateQueries({ queryKey: ['event-discord', eventId] })
    queryClient.invalidateQueries({ queryKey: ['event-task-schedule', eventId] })
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
git add frontend/app/hooks/useEvent.ts frontend/tests/playwright/
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

**Spec coverage check (Q1–Q13):**
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
- Q11 lease pattern (Option B — worker passes channel_id + embed_data at claim time) → Tasks 1.2 (schema with partial unique on `success IS NOT FALSE`), 1.2.5 (claim/finalize helpers + sync_send_embed refactor with auth via existing `_auth`/`_perm` decorators), 1.3 (reminder tasks; `send_subscriber_notifications` gets explicit lease bracketing since it uses `sync_send_dm` not `sync_send_embed`), 1.4/1.5 (extracted reminder tasks), 1.13 (concurrency test), 1.13.5 (60s sweeper handling both NULL pending AND aged-out failures)
- Q12 frontend deploy ordering → Phase 0 (expanded Task 0.1) ships before Phase 1
- Q13 cacheops invalidate_model → Task 1.14 (runbook)

**Second-pass review-finding coverage (Severity 1 — design):**
- IntegrityError after-send → replaced by lease pattern across Tasks 1.2 / 1.2.5 / 1.3 / 1.4 / 1.5 / 1.13
- Lost-the-race semantics now actually prevent duplicate Discord sends, not just duplicate audit rows

**Severity 2 (code conventions):**
- Raw `invalidate_obj` → switched to `invalidate_after_commit` from `app.cache_utils` per project convention (Task 1.10)
- Task 1.12 was redundant → converted to a regression test asserting existing behavior
- Nested `transaction.atomic` in sync_future_events → removed (function is already decorated)
- Task 1.13 concurrency test models the right race (parallel reminder tasks, not parallel polls)
- Task 1.6 registry test now imports `events.tasks` explicitly so `current_app.tasks.get(name)` works in CI

**Severity 3 (frontend):**
- Vitest test paths fixed to co-located `__tests__/` directories so `app/**/*.test.ts` glob picks them up (Tasks 0.1, 2.4)
- Path alias `~/` used (not `@/`) per project convention (Tasks 0.1, 2.4)
- Discriminated union → `superRefine` (Task 2.4) — works on actual API payload shape
- PR-0 expanded to include modal defaultValues + eventsAPI.ts interface updates so `tsc` doesn't break (Task 0.1)
- `useEvent.ts` path corrected to `frontend/app/hooks/useEvent.ts` (Task 2.6)
- `eventId` closure used instead of `variables.id` per file's existing convention (Task 2.6)

**Severity 4 (deploy):**
- Runbook reordered: migrate → invalidate_model → restart workers → restart beat (Task 1.14)
- Beat-vs-worker rolling-deploy guidance explicit (Task 1.14)
- Stale-lease sweeper added at 60s cadence with dual-mode handling (Task 1.13.5)

**Third-pass review-finding coverage:**
- C1 (lease INSERT violates non-null fields): Resolved by Option B — worker passes `channel_id` + `embed_data` at claim time (Tasks 1.2, 1.2.5). `_row()` test helper supplies both.
- `send_subscriber_notifications` not lease-protected: Task 1.3 Step 4 wraps the entire DM loop in explicit claim/finalize.
- `@csrf_exempt` regression: Task 1.2.5 Step 4 uses the project's existing `@authentication_classes(_auth) @permission_classes(_perm)` decorator stack.
- `base_fields` placeholder: Task 1.10 enumerates the actual `["name", "description"]` shared fields plus the three mixin-introspected `*_FIELDS` constants from `services.py:530-538`.
- `_compute_occurrence_datetime` TODO: Task 2.1 reuses the existing `_get_next_occurrences` helper at `services.py:551`. No new helper needed.
- Task 1.10 cascade reframed: `DISCORD_CONFIG_FIELDS` is auto-built from `DiscordEventConfigMixin._meta.get_fields()` (line 536-538), so the cascade was always automatic. Task 1.10 just adds `invalidate_after_commit` and a list return; new mixin-coverage CI test ensures registry fields stay on the mixin.
- Task 1.6 registry test imports `events.tasks` explicitly to avoid vacuous pass under `current_app.tasks.get` lookups.
- Task 1.8 mock target corrected: `events.scheduling.fire.fire_due_reminders` (where the lookup happens at call time), not `events.tasks.fire_due_reminders`.
- Task 1.8 stale-comment text rewritten to reference the lease pattern, not the rejected partial-index-after-send design.
- Task 1.9 explicitly addresses other call sites of `send_event_announcement` (TASK_MAP at views.py:1184, tasks.py:150) — preserved as manual-trigger paths protected by the lease.
- Task 0.1 cleans `DISCORD_CONFIG_DEFAULTS` constant in `schemas.ts` (the spread source for all 4 modals' `defaultValues`).
- Task 0.1 path corrected: `frontend/app/components/api/eventsAPI.ts`. Interfaces are `EventRepeaterType` and `OrgEventDefaultsType` (no `Event` interface in this file).
- Task 2.3 fixes hardcoded `isRepeater={false}` on EditEventModal:422.
- Task 2.6 path is `frontend/app/hooks/useEvent.ts:185` (verified — code-reviewer was wrong on this one; v3 path was correct).
- Task 1.2 unique constraint is now PARTIAL on `success IS NOT FALSE`, so transient Discord failures don't permanently brick reminders. The 1-hour failure-aging in the sweeper bounds the retry budget.
- Task 1.2 Step 7 adds a pre-flight check for pre-existing duplicates that would block the migration.
- Task 1.13.5 cadence reduced to 60s (vs 5min) to keep total worker-crash recovery latency <1.5 min.

**Placeholder scan:** No "TBD" / "implement later" / generic "add error handling" found. Each task code block is complete and self-contained.

**Type consistency:** `ScheduledReminder.task_name` (str) is used consistently across Task 1.6, 1.7, and the CI tests. Lease helper names `claim_discord_message_log` / `finalize_discord_message_log` are consistent across Tasks 1.2.5, 1.3, 1.4, 1.5, 1.13.
