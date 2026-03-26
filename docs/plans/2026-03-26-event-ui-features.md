# Event UI Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add org timezone editing, events page repeater tab, per-event task schedule view, and discord log detail modal.

**Architecture:** Backend already has timezone on Organization serializer. New `GET /api/events/{id}/task-schedule/` endpoint calculates task projections from event config. Frontend adds tabs, modals, and timeline components using existing Shadcn UI patterns.

**Tech Stack:** Django REST Framework, React, TypeScript, Shadcn UI (Tabs, Dialog, Badge, ScrollArea), Zustand, TanStack Query.

---

## Review Fixes Applied

| Issue | Resolution |
|-------|-----------|
| Missing tasks in schedule (only 6 of 11+) | Added all task types: reconciliation, signup update, new event notification, open signups, generate events |
| ROLL_CALL state missing for attendance/subscriber tasks | Fixed `fires_at` to account for both SIGNUPS_OPEN and ROLL_CALL states |
| Missing `data-testid` on sub-tabs, task rows, modal | Added testids for every interactive element |
| Lifecycle test clicks Discord tab twice | Removed redundant click, use `data-testid` selectors |
| `embed_data` doesn't exist on DiscordEventLog | Modal shows `response_data` + `error_message` only (available fields) |
| Sub-tabs hide status cards | Keep status cards above sub-tabs (always visible) |
| `useEventTaskSchedule` uses raw axios | Import API function from `~/components/api/api` |
| `next_event_date` not in repeater serializer | Add annotation to viewset |
| Timezone missing from EditOrganizationSchema | Add `timezone: z.string().optional()` |
| Status badge colors don't match theme | Use `bg-{color}/20 text-{color}` pattern from EventStateBadge |
| Reuse COMMON_TIMEZONES | Import from tournament/schemas |
| Icons not specified | Lucide: CheckCircle/Clock/AlertCircle/Circle |

---

## Theming Reference

Status badges use the `bg-{color}/20 text-{color} border-{color}/30` pattern:
- **Fired**: `bg-success/20 text-success border-success/30` + CheckCircle icon
- **Pending**: `bg-warning/20 text-warning border-warning/30` + Clock icon
- **Ready**: `bg-info/20 text-info border-info/30` + AlertCircle icon
- **Disabled**: `bg-muted text-muted-foreground border-border` + Circle icon

Buttons: PrimaryButton for CTAs, SecondaryButton for context actions. Never raw `<Button>`.

---

## Task 1: Org Default Timezone in Edit Modal

**Files:**
- Modify: `frontend/app/components/organization/schemas.ts` (add timezone to EditOrganizationSchema)
- Modify: `frontend/app/components/organization/forms/EditOrganizationModal.tsx` (add Select)

**Step 1:** Add `timezone` to `EditOrganizationSchema`:
```typescript
timezone: z.string().optional().default('America/New_York'),
```

**Step 2:** Import `COMMON_TIMEZONES` from `~/components/tournament/schemas`.

**Step 3:** Add timezone Select field to the form (between description and discord_link):
```tsx
<FormField control={form.control} name="timezone" render={({ field }) => (
  <FormItem>
    <FormLabel>Default Timezone</FormLabel>
    <Select onValueChange={field.onChange} value={field.value}>
      <FormControl>
        <SelectTrigger className="w-full" data-testid="org-timezone-select">
          <SelectValue placeholder="Select timezone" />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        {COMMON_TIMEZONES.map((tz) => (
          <SelectItem key={tz} value={tz}>{tz}</SelectItem>
        ))}
      </SelectContent>
    </Select>
    <FormMessage />
  </FormItem>
)} />
```

**Step 4:** Add timezone to form `defaultValues` and `reset()` call.

**Step 5:** Commit.
```
git commit -m "feat: add timezone select to EditOrganizationModal"
```

---

## Task 2: Events Page — Repeaters Tab

**Files:**
- Modify: `frontend/app/routes/events.tsx`
- Create: `frontend/app/components/events/RepeaterCard.tsx`
- Modify: `frontend/app/hooks/useEvent.ts` (add useRepeaters query)
- Modify: `backend/events/views.py` (annotate next_event_date on repeater queryset)

**Step 1:** Backend — annotate `next_event_date` on EventRepeaterViewSet:
```python
from django.db.models import Min, Q
from events.models import Event, EventState

qs = qs.annotate(
    next_event_date=Min(
        "events__scheduled_at",
        filter=Q(events__state__in=[EventState.UPCOMING, EventState.SIGNUPS_OPEN]),
    ),
)
```
Add `next_event_date` to EventRepeaterSerializer as `serializers.DateTimeField(read_only=True, default=None)`.

**Step 2:** Frontend — add `useRepeaters` hook:
```typescript
export function useRepeaters(orgId?: number) {
  return useQuery({
    queryKey: ['repeaters', orgId],
    queryFn: () => api.get('/events/repeaters/', { params: orgId ? { organization: orgId } : {} }).then(r => r.data),
    enabled: true,
  });
}
```

**Step 3:** Create `RepeaterCard.tsx`:
```tsx
// Frequency badge: bg-primary/20 text-primary
// Active: bg-success/20 text-success | Inactive: bg-muted text-muted-foreground
// Subscriber count + next event date
// Click → navigate to /organizations/{orgId}
// data-testid="repeater-card-{id}"
```

**Step 4:** Wrap events page in Tabs:
```tsx
<Tabs defaultValue="events">
  <TabsList>
    <TabsTrigger value="events" data-testid="events-tab-events">Events</TabsTrigger>
    <TabsTrigger value="series" data-testid="events-tab-series">Series</TabsTrigger>
  </TabsList>
  <TabsContent value="events">{/* existing event list */}</TabsContent>
  <TabsContent value="series">{/* RepeaterCard grid */}</TabsContent>
</Tabs>
```

**Step 5:** Commit.
```
git commit -m "feat: add Series tab to events page with RepeaterCard"
```

---

## Task 3: Backend — Task Schedule Endpoint

**Files:**
- Modify: `backend/events/views.py`
- Modify: `backend/backend/urls.py`
- Test: `backend/app/tests/test_task_schedule.py`

**What:** `GET /api/events/{id}/task-schedule/` — returns ALL projected tasks for an event, including periodic reconciliation tasks and on-demand triggers.

**Full task list (11 types):**

| Task | Label | Trigger | fires_at calculation |
|------|-------|---------|---------------------|
| announcement | Discord Announcement | State → SIGNUPS_OPEN | None (state-triggered) |
| signup_post | Signup Post | State → SIGNUPS_OPEN | None (state-triggered) |
| scheduled_event | Discord Scheduled Event | sync_discord_events (every 5m) | None (sync-triggered) |
| signup_reminder | Signup Reminder | check_event_reminders (30s) | scheduled_at - signup_reminder_hours |
| confirm_attendance | Attendance Reminder | check_event_reminders (30s) | scheduled_at - confirm_attendance_hours |
| profile_reminder | Profile Reminder | check_event_reminders (30s) | scheduled_at - profile_reminder_hours |
| subscriber_dm | Subscriber DM | check_event_reminders (30s) | scheduled_at - subscriber_dm_hours |
| signup_update | Signup Update | On each signup change | N/A (event-triggered) |
| new_event_notification | New Event Notice | On repeater generation | N/A (generation-triggered) |
| sync_reconciliation | Discord Sync | sync_discord_events (every 5m) | Recurring |
| open_signups | Auto-Open Signups | open_scheduled_signups (1m) | signups_open_at |

**Status determination:**
- Check `DiscordMessageLog` for `source` matching the task's `log_source`
- Check `DiscordEventLog` for matching `action`
- Check `DiscordEventDM` for subscriber DMs
- Account for BOTH `signups_open` AND `roll_call` states for attendance/subscriber tasks
- Empty `announcement_channel_id` with `discord_announcement=True` → show as "misconfigured"

**Step 1: Write failing test** (see original plan — updated to test 11 task types)

**Step 2: Implement endpoint** with full task list and correct state checks

**Step 3: Wire URL:**
```python
path("api/events/<int:event_id>/task-schedule/", get_event_task_schedule),
```

**Step 4: Commit.**
```
git commit -m "feat: add GET /api/events/{id}/task-schedule/ with 11 task projections"
```

---

## Task 4: Frontend — Task Schedule Timeline

**Files:**
- Create: `frontend/app/components/events/TaskScheduleSection.tsx`
- Modify: `frontend/app/components/events/DiscordLogSection.tsx` (add sub-tabs BELOW status cards)
- Modify: `frontend/app/hooks/useEvent.ts` (add useEventTaskSchedule)
- Modify: `frontend/app/components/api/api.tsx` (add getEventTaskSchedule)

**Step 1:** Add API function:
```typescript
// In api.tsx
export async function getEventTaskSchedule(eventId: number) {
  const resp = await api.get(`/events/${eventId}/task-schedule/`);
  return resp.data;
}
```

**Step 2:** Add TanStack Query hook:
```typescript
export function useEventTaskSchedule(eventId: number | null) {
  return useQuery({
    queryKey: ['event-task-schedule', eventId],
    queryFn: () => getEventTaskSchedule(eventId!),
    enabled: !!eventId,
  });
}
```

**Step 3:** Create `TaskScheduleSection.tsx`:
- Each task row: icon + label + fires_at (relative time via `formatDistanceToNow`) + status badge
- Icons: CheckCircle (fired), Clock (pending), AlertCircle (ready), Circle (disabled)
- Status badges use theme tokens (see Theming Reference above)
- Sort: fired first, then by fires_at (soonest), disabled last
- `data-testid="task-schedule-entry-{task}"` on each row
- `data-testid="task-schedule-section"` on container

**Step 4:** Restructure DiscordLogSection with sub-tabs:
```tsx
{/* Status cards — ALWAYS VISIBLE (above tabs) */}
<div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
  {/* Signup Post card, Announcement card, Scheduled Event card */}
</div>

{/* Sub-tabs for different views */}
<Tabs defaultValue="schedule">
  <TabsList>
    <TabsTrigger value="schedule" data-testid="discord-subtab-schedule">
      Task Schedule
    </TabsTrigger>
    <TabsTrigger value="activity" data-testid="discord-subtab-activity">
      Activity Log
    </TabsTrigger>
    <TabsTrigger value="dms" data-testid="discord-subtab-dms">
      DM History
    </TabsTrigger>
  </TabsList>
  <TabsContent value="schedule"><TaskScheduleSection eventId={eventId} /></TabsContent>
  <TabsContent value="activity">{/* existing activity log with category filters */}</TabsContent>
  <TabsContent value="dms">{/* existing DM history */}</TabsContent>
</Tabs>
```

**Step 5:** Commit.
```
git commit -m "feat: add Task Schedule sub-tab to Discord section with 11 task types"
```

---

## Task 5: Discord Log Detail Modal

**Files:**
- Create: `frontend/app/components/events/DiscordLogDetailModal.tsx`
- Modify: `frontend/app/components/events/DiscordLogSection.tsx` (make rows clickable)

**Available fields on DiscordEventLog** (NOT DiscordMessageLog):
- `action`, `target_type`, `success`, `status_code`
- `response_data` (JSON — Discord API response)
- `error_message` (text)
- `discord_user_id`, `discord_username`
- `message_id`, `created_at`, `category`

**Does NOT have**: `embed_data` (that's on DiscordMessageLog only)

**Step 1:** Create `DiscordLogDetailModal`:
```tsx
interface Props {
  log: DiscordLogEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  repeaterName?: string;
}
```

**Compact section (always visible):**
- Status: `<Badge>` with success/error theming
- Action + target type
- Timestamp (absolute + relative)
- Discord message ID (if present — clickable link)
- Repeater name (if event has `event_repeater`)
- HTTP status code
- Discord user (if `discord_username` present)

**Expandable "Raw Response" (Collapsible, `data-testid="discord-log-raw-data"`)**:
- `response_data` JSON in `<pre>` block (NOT embed_data — doesn't exist on this model)
- `error_message` if present
- Log PK for reference

**Step 2:** Make activity log entries clickable:
```tsx
<div
  data-testid={`discord-log-entry-${entry.id}`}
  className="cursor-pointer hover:bg-base-400/30 rounded p-2 transition-colors"
  onClick={() => setSelectedLog(entry)}
>
  {/* existing entry content */}
</div>
```

**Step 3:** Add modal state + render:
```tsx
const [selectedLog, setSelectedLog] = useState<DiscordLogEntry | null>(null);
// ...
<DiscordLogDetailModal
  log={selectedLog}
  open={!!selectedLog}
  onOpenChange={(open) => !open && setSelectedLog(null)}
  repeaterName={discordState?.event_repeater_name}
  data-testid="discord-log-detail-modal"
/>
```

**Step 4:** Commit.
```
git commit -m "feat: add Discord log detail modal with raw response data"
```

---

## Task 6: Lifecycle Test Extension

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/06-full-lifecycle.spec.ts`

**Step 1:** After the existing step 13 (which already clicks Discord tab at line 275), add task schedule verification. Do NOT click Discord tab again — it's already active:

```typescript
// 14. Verify Task Schedule on Discord tab (already active from step 13)
const scheduleTab = page.getByTestId('discord-subtab-schedule');
await expect(scheduleTab).toBeVisible({ timeout: 5000 });
await scheduleTab.click();

// Should show task entries for configured notifications
await expect(page.getByTestId('task-schedule-section')).toBeVisible({ timeout: 5000 });
await expect(page.getByTestId('task-schedule-entry-announcement')).toBeVisible();

// 15. Click a log entry to verify detail modal
await page.getByTestId('discord-subtab-activity').click();
const firstLogEntry = page.locator('[data-testid^="discord-log-entry-"]').first();
if (await firstLogEntry.isVisible({ timeout: 3000 }).catch(() => false)) {
  await firstLogEntry.click();
  await expect(page.getByTestId('discord-log-detail-modal')).toBeVisible({ timeout: 3000 });
  await page.keyboard.press('Escape');
}
```

**Step 2:** Commit.
```
git commit -m "test: verify task schedule and log detail modal in lifecycle E2E test"
```

---

## Task Order

| Task | Depends On | Effort | Parallel? |
|------|-----------|--------|-----------|
| 1. Org timezone edit | None | Small | Yes |
| 2. Events page repeater tab | None | Medium | Yes |
| 3. Task schedule endpoint | None | Medium | Yes |
| 4. Task schedule UI | Task 3 | Medium | No |
| 5. Discord log detail modal | None | Medium | Yes |
| 6. Lifecycle test | Tasks 3, 4, 5 | Small | No |

Tasks 1, 2, 3, 5 are independent — can run in parallel.
Task 4 requires Task 3. Task 6 requires Tasks 3+4+5.
