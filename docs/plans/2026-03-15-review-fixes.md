# Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all issues identified by the 3-agent review: auth bypass, channel ID validation, DRY violations, responsive grids, accessibility, and UI polish.

**Architecture:** Backend auth fixes in views.py, model-level validators for Discord IDs, frontend DRY extraction of shared schemas/defaults/constants into schemas.ts, UI fixes across modals and components.

**Tech Stack:** Django REST Framework, Zod, React Hook Form, Tailwind CSS

---

### Task 1: Fix auth bypass on EventViewSet and EventRepeaterViewSet

**Files:**
- Modify: `backend/events/views.py`

Both `perform_create` methods need org staff checks. DRF's `has_object_permission` is not called during `create` because the object doesn't exist yet.

**Fix both `perform_create` methods:**

```python
# EventRepeaterViewSet.perform_create (line 72)
def perform_create(self, serializer):
    org = serializer.validated_data.get("organization")
    if not has_org_staff_access(self.request.user, org):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("You do not have staff access to this organization.")
    serializer.save(created_by=self.request.user)

# EventViewSet.perform_create (line 98)
def perform_create(self, serializer):
    org = serializer.validated_data.get("organization")
    if not has_org_staff_access(self.request.user, org):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("You do not have staff access to this organization.")
    serializer.save(created_by=self.request.user)
```

Import `PermissionDenied` at the top instead of inline:
```python
from rest_framework.exceptions import PermissionDenied
```

---

### Task 2: Add Discord snowflake validation on channel ID fields

**Files:**
- Modify: `backend/events/models.py`

Add a regex validator to `DiscordEventConfigMixin` for both channel ID fields:

```python
from django.core.validators import RegexValidator

discord_id_validator = RegexValidator(
    r'^\d{17,20}$',
    'Must be a valid Discord snowflake ID',
)
```

Apply to both fields (allow blank since they default to ""):

```python
discord_post_signups_channel_id = models.CharField(
    max_length=20,
    blank=True,
    default="",
    validators=[discord_id_validator],
    help_text="Discord channel ID to post signup embed in",
)
discord_announcement_channel_id = models.CharField(
    max_length=20,
    blank=True,
    default="",
    validators=[discord_id_validator],
    help_text="Discord channel ID for pre-day announcement",
)
```

Note: The validator allows blank because `blank=True` + `default=""`. Django's `RegexValidator` won't fire on empty strings when `blank=True` is set on the model. But to be safe, update the regex to also allow empty string:

```python
discord_id_validator = RegexValidator(
    r'^(\d{17,20})?$',
    'Must be a valid Discord snowflake ID',
)
```

Run `just py::manage makemigrations events` — this will create a new migration since validators are part of the field definition.

---

### Task 3: Fix f-string in log statement

**Files:**
- Modify: `backend/discordbot/services/channels.py`

Change line 74:
```python
# Before
log.error(f"Failed to fetch Discord channels for org {org.pk}: {e}")
# After
log.error("Failed to fetch Discord channels for org %s: %s", org.pk, e)
```

---

### Task 4: Extract shared Discord Zod schema, defaults, and constants

**Files:**
- Modify: `frontend/app/components/events/schemas.ts`
- Modify: `frontend/app/components/events/EditEventModal.tsx`
- Modify: `frontend/app/components/events/EditRepeaterModal.tsx`
- Modify: `frontend/app/components/events/CreateEventModal.tsx`

**Step 1: Add shared schema and defaults to `schemas.ts`**

Add after the `Frequency` constant and before `createEventInputSchema`:

```typescript
export const FREQUENCY_LABELS: Record<string, string> = {
  [Frequency.DAILY]: 'Daily',
  [Frequency.WEEKLY]: 'Weekly',
  [Frequency.EVERY_TWO_WEEKS]: 'Every Two Weeks',
  [Frequency.MONTHLY]: 'Monthly',
};

export const DAY_LABELS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

export const discordConfigSchema = z.object({
  discord_create_event: z.boolean(),
  discord_sync_signups: z.boolean(),
  discord_event_title: z.string(),
  discord_event_description: z.string(),
  discord_event_info: z.string(),
  discord_signup_reminder: z.boolean(),
  discord_signup_reminder_hours: z.number().int().min(1),
  discord_confirm_attendance: z.boolean(),
  discord_profile_reminder: z.boolean(),
  discord_mark_interested: z.boolean(),
  discord_post_signups: z.boolean(),
  discord_post_signups_channel_id: z.string(),
  discord_announcement: z.boolean(),
  discord_announcement_channel_id: z.string(),
  discord_announcement_hours: z.number().int().min(1),
});

export const DISCORD_CONFIG_DEFAULTS = {
  discord_create_event: false,
  discord_sync_signups: false,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_signup_reminder: false,
  discord_signup_reminder_hours: 24,
  discord_confirm_attendance: false,
  discord_profile_reminder: false,
  discord_mark_interested: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
} as const;
```

**Step 2: Refactor `createEventInputSchema` to use `discordConfigSchema`**

Replace the inline discord fields with `.merge()`:

```typescript
export const createEventInputSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  scheduled_at: z.string(),
  organization: z.number(),
  tournament_league: z.number({ error: 'League is required' }),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
  discord_notify_new_events: z.boolean().optional(),
  // Recurring fields
  is_recurring: z.boolean(),
  frequency: z.string().optional(),
  day_of_week: z.number().int().min(0).max(6).optional(),
  time_of_day: z.string().optional(),
  starts_at: z.string().optional(),
  ends_at: z.string().optional(),
  generate_days_ahead: z.number().int().min(1),
}).merge(discordConfigSchema);
```

**Step 3: Refactor EditEventModal to use shared schema + defaults**

Replace the local `editEventSchema` discord fields with `.merge()`:

```typescript
import { discordConfigSchema, DISCORD_CONFIG_DEFAULTS } from './schemas';

const editEventSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  scheduled_at: z.string().min(1, 'Scheduled date is required'),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
}).merge(discordConfigSchema);
```

Replace inline discord defaults in `useForm` with `...DISCORD_CONFIG_DEFAULTS`.

**Step 4: Refactor EditRepeaterModal to use shared schema + defaults**

Same pattern:

```typescript
import { discordConfigSchema, DISCORD_CONFIG_DEFAULTS, Frequency, FREQUENCY_LABELS, DAY_LABELS } from './schemas';

const editRepeaterSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
  frequency: z.string(),
  day_of_week: z.number().int().min(0).max(6).optional(),
  time_of_day: z.string(),
  ends_at: z.string().optional(),
  generate_days_ahead: z.number().int().min(1),
  discord_notify_new_events: z.boolean(),
}).merge(discordConfigSchema);
```

Remove local `FREQUENCY_LABELS` and `DAY_LABELS` — import from `./schemas`.

**Step 5: Refactor CreateEventModal**

Import `DISCORD_CONFIG_DEFAULTS, FREQUENCY_LABELS, DAY_LABELS` from `./schemas`. Remove local constants. Spread `...DISCORD_CONFIG_DEFAULTS` in `useForm` defaultValues.

---

### Task 5: Fix frontend UI issues

**Files:**
- Modify: `frontend/app/components/events/CreateEventModal.tsx`
- Modify: `frontend/app/components/events/EditRepeaterModal.tsx`
- Modify: `frontend/app/components/events/DiscordChannelPicker.tsx`

**Step 1: Fix responsive grids on schedule fields**

In CreateEventModal, change:
- `grid-cols-2 gap-4` → `grid-cols-1 sm:grid-cols-2 gap-4` (Frequency/Day row)
- `grid-cols-3 gap-4` → `grid-cols-1 sm:grid-cols-3 gap-4` (Time/Starts/Ends row)

Same changes in EditRepeaterModal.

**Step 2: Replace raw `<p>` tags with `<FormDescription>`**

In CreateEventModal, replace:
```tsx
<p className="text-xs text-muted-foreground">
  Automatically generates events on a schedule
</p>
```
with `<FormDescription>Automatically generates events on a schedule</FormDescription>`

And:
```tsx
<p className="text-xs text-muted-foreground">
  How many days in advance to generate events
</p>
```
with `<FormDescription>How many days in advance to generate events</FormDescription>`

Add `FormDescription` to the form import if not already there.

**Step 3: Add empty state to DiscordChannelPicker**

Inside `SelectContent`, after the error div and before `channels.map()`:

```tsx
{channels.length === 0 && !error && !loading && (
  <div className="px-2 py-1.5 text-sm text-muted-foreground">No text channels found</div>
)}
```

---

### Task 6: Verify all fixes

```bash
cd /home/kettle/git_repos/website/.worktrees/events && just py::manage check
cd /home/kettle/git_repos/website/.worktrees/events && just py::manage makemigrations --check
npx tsc --noEmit 2>&1 | grep "app/components/events/"
```

---

## Files Summary

| File | Change |
|------|--------|
| `backend/events/views.py` | Auth check in both `perform_create` methods |
| `backend/events/models.py` | Discord snowflake validator on channel ID fields |
| `backend/events/migrations/0007_*.py` | Auto-generated for validator change |
| `backend/discordbot/services/channels.py` | Lazy log formatting |
| `frontend/app/components/events/schemas.ts` | Extract `discordConfigSchema`, `DISCORD_CONFIG_DEFAULTS`, `FREQUENCY_LABELS`, `DAY_LABELS` |
| `frontend/app/components/events/CreateEventModal.tsx` | Use shared constants, fix responsive grids, FormDescription |
| `frontend/app/components/events/EditEventModal.tsx` | Use shared schema + defaults |
| `frontend/app/components/events/EditRepeaterModal.tsx` | Use shared schema + defaults + constants, fix responsive grids |
| `frontend/app/components/events/DiscordChannelPicker.tsx` | Add empty state |
