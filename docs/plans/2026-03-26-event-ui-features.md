# Event UI Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add org timezone editing, events page repeater tab, per-event task schedule view, and discord log detail modal.

**Architecture:** Backend already has timezone on Organization serializer. New `GET /api/events/{id}/task-schedule/` endpoint calculates task projections from event config. Frontend adds tabs, modals, and timeline components using existing Shadcn UI patterns.

**Tech Stack:** Django REST Framework, React, TypeScript, Shadcn UI (Tabs, Dialog, Badge, ScrollArea), Zustand, TanStack Query.

---

## Task 1: Org Default Timezone in Edit Modal

**Files:**
- Modify: `frontend/app/components/organization/forms/EditOrganizationModal.tsx`
- Modify: `frontend/app/components/organization/schemas.ts` (if timezone not in schema)

**What:** Add a timezone Select dropdown to the EditOrganizationModal. The `Organization.timezone` field and serializer already exist — this is frontend-only.

**Step 1:** Check if `timezone` is in the EditOrganizationSchema. If not, add it.

**Step 2:** Add timezone Select to the form, using the same timezone options as CreateEventModal (reuse `TIMEZONE_OPTIONS` if it exists, or create a shared constant).

**Step 3:** Verify the PATCH request includes timezone. Test manually via UI.

**Step 4:** Commit.

```
git commit -m "feat: add timezone select to EditOrganizationModal"
```

---

## Task 2: Events Page — Repeaters Tab

**Files:**
- Modify: `frontend/app/routes/events.tsx`
- Create: `frontend/app/components/events/RepeaterCard.tsx`

**What:** Add two tabs to the events list page: "Events" (existing) and "Series" (repeaters).

**Step 1:** Wrap existing events list content in a `<Tabs>` component with "events" and "series" values.

**Step 2:** Create `RepeaterCard` component showing:
- Repeater name (heading)
- Organization name + logo (HighlightButton or badge)
- Frequency badge ("Weekly", "Daily", "Biweekly")
- Subscriber count
- Active/inactive badge
- Click navigates to `/organizations/{orgId}` events tab

**Step 3:** In the "Series" tab content, fetch repeaters via `GET /api/events/repeaters/` (with org filter if selected). Render as a grid of RepeaterCards.

**Step 4:** Test: verify both tabs render, org filter works on both tabs.

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

**What:** `GET /api/events/{id}/task-schedule/` — returns projected task timeline for an event.

**Step 1: Write the failing test**

```python
# backend/app/tests/test_task_schedule.py
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta
from app.models import Organization
from events.models import Event

class TaskScheduleEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Schedule Test Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Schedule Test Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=True,
            discord_signup_reminder_hours=6,
            discord_confirm_attendance=True,
            discord_confirm_attendance_hours=3,
            discord_announcement=True,
            discord_announcement_channel_id="123",
            discord_subscriber_dm=True,
            discord_subscriber_dm_hours=12,
        )
        # Login as admin
        from tests.test_auth import createAdminTestUser
        user, _ = createAdminTestUser()
        self.client.force_authenticate(user=user)

    def test_returns_projected_tasks(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        self.assertIsInstance(tasks, list)
        # Should have entries for each enabled notification
        task_names = [t["task"] for t in tasks]
        self.assertIn("signup_reminder", task_names)
        self.assertIn("confirm_attendance", task_names)
        self.assertIn("announcement", task_names)
        self.assertIn("subscriber_dm", task_names)

    def test_includes_fires_at(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertIn("fires_at", reminder)
        self.assertIsNotNone(reminder["fires_at"])

    def test_disabled_tasks_show_disabled_status(self):
        self.event.discord_profile_reminder = False
        self.event.save()
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        profile = next((t for t in tasks if t["task"] == "profile_reminder"), None)
        # Disabled tasks either don't appear or show status=disabled
        if profile:
            self.assertEqual(profile["status"], "disabled")
```

**Step 2: Run test to verify it fails**

```bash
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py test app.tests.test_task_schedule -v 2
```

**Step 3: Implement endpoint**

```python
# In backend/events/views.py — add new endpoint

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_event_task_schedule(request, event_id):
    """Return projected task timeline for an event.

    Calculates when each notification/reminder will fire based on the
    event's Discord config and scheduled_at time. Checks DiscordMessageLog
    and DiscordEventLog to determine if tasks have already fired.
    """
    from discordbot.models import DiscordEventLog, DiscordMessageLog

    event = Event.objects.get(pk=event_id)
    now = timezone.now()
    tasks = []

    # Define task projections based on event config
    TASK_DEFS = [
        {
            "task": "announcement",
            "label": "Discord Announcement",
            "enabled": event.discord_announcement and bool(event.discord_announcement_channel_id),
            "fires_at": None,  # fires on state transition to signups_open
            "log_source": "event_announcement",
        },
        {
            "task": "signup_reminder",
            "label": "Signup Reminder",
            "enabled": event.discord_signup_reminder,
            "fires_at": event.scheduled_at - timedelta(hours=event.discord_signup_reminder_hours) if event.discord_signup_reminder else None,
            "log_source": "signup_reminder",
        },
        {
            "task": "confirm_attendance",
            "label": "Attendance Reminder",
            "enabled": event.discord_confirm_attendance,
            "fires_at": event.scheduled_at - timedelta(hours=event.discord_confirm_attendance_hours) if event.discord_confirm_attendance else None,
            "log_source": "attendance_reminder",
        },
        {
            "task": "profile_reminder",
            "label": "Profile Reminder",
            "enabled": event.discord_profile_reminder,
            "fires_at": event.scheduled_at - timedelta(hours=event.discord_profile_reminder_hours) if event.discord_profile_reminder else None,
            "log_source": "profile_reminder",
        },
        {
            "task": "subscriber_dm",
            "label": "Subscriber DM",
            "enabled": event.discord_subscriber_dm,
            "fires_at": event.scheduled_at - timedelta(hours=event.discord_subscriber_dm_hours) if event.discord_subscriber_dm else None,
            "log_source": None,  # uses DiscordEventDM model
        },
        {
            "task": "scheduled_event",
            "label": "Discord Scheduled Event",
            "enabled": event.discord_create_event,
            "fires_at": None,  # fires on signups_open via sync
            "log_source": "create_discord_event",
        },
    ]

    # Check which tasks have already fired
    fired_sources = set(
        DiscordMessageLog.objects.filter(
            source_id=event.pk,
            success=True,
        ).values_list("source", flat=True)
    )

    # Check DiscordEventLog too
    try:
        discord_event = event.discord_event
        fired_actions = set(
            DiscordEventLog.objects.filter(
                discord_event=discord_event,
                success=True,
            ).values_list("action", flat=True)
        )
    except Exception:
        fired_actions = set()

    # Check subscriber DMs
    from discordbot.models import DiscordEventDM, DMType
    has_dms = DiscordEventDM.objects.filter(
        discord_event__event=event,
        dm_type=DMType.SIGNUP_REMINDER,
    ).exists()

    for td in TASK_DEFS:
        if not td["enabled"]:
            tasks.append({
                "task": td["task"],
                "label": td["label"],
                "fires_at": None,
                "status": "disabled",
            })
            continue

        # Determine status
        if td["task"] == "subscriber_dm":
            status = "fired" if has_dms else ("pending" if td["fires_at"] and now < td["fires_at"] else "ready")
        elif td["log_source"] in fired_sources:
            status = "fired"
        elif td["task"] == "scheduled_event" and "create_scheduled_event" in fired_actions:
            status = "fired"
        elif td["fires_at"] and now < td["fires_at"]:
            status = "pending"
        else:
            status = "ready"  # should fire soon

        tasks.append({
            "task": td["task"],
            "label": td["label"],
            "fires_at": td["fires_at"].isoformat() if td["fires_at"] else None,
            "status": status,
        })

    return Response(tasks)
```

Wire URL:
```python
path("api/events/<int:event_id>/task-schedule/", get_event_task_schedule),
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```
git commit -m "feat: add GET /api/events/{id}/task-schedule/ endpoint"
```

---

## Task 4: Frontend — Task Schedule Timeline Component

**Files:**
- Create: `frontend/app/components/events/TaskScheduleSection.tsx`
- Modify: `frontend/app/components/events/DiscordLogSection.tsx` (add sub-tabs)
- Modify: `frontend/app/hooks/useEvent.ts` (add useEventTaskSchedule query)

**What:** New sub-tab within the Discord tab showing the task timeline.

**Step 1:** Add TanStack Query hook:
```typescript
export function useEventTaskSchedule(eventId: number | null) {
  return useQuery({
    queryKey: ['event-task-schedule', eventId],
    queryFn: () => axios.get(`/events/${eventId}/task-schedule/`).then(r => r.data),
    enabled: !!eventId,
  });
}
```

**Step 2:** Create `TaskScheduleSection` component:
- Fetch via `useEventTaskSchedule(eventId)`
- Render each task as a row: icon + label + fires_at (relative time) + status badge
- Status badges: "Fired" (green), "Pending" (yellow), "Ready" (blue), "Disabled" (gray)
- Sort by fires_at (earliest first), disabled at bottom

**Step 3:** Add sub-tabs to DiscordLogSection:
```tsx
<Tabs defaultValue="schedule">
  <TabsList>
    <TabsTrigger value="schedule">Task Schedule</TabsTrigger>
    <TabsTrigger value="activity">Activity Log</TabsTrigger>
    <TabsTrigger value="dms">DM History</TabsTrigger>
  </TabsList>
  <TabsContent value="schedule"><TaskScheduleSection eventId={eventId} /></TabsContent>
  <TabsContent value="activity">{/* existing activity log */}</TabsContent>
  <TabsContent value="dms">{/* existing DM history */}</TabsContent>
</Tabs>
```

**Step 4:** Test manually: navigate to event with Discord config, verify schedule appears.

**Step 5:** Commit.

```
git commit -m "feat: add Task Schedule sub-tab to Discord section"
```

---

## Task 5: Discord Log Detail Modal

**Files:**
- Create: `frontend/app/components/events/DiscordLogDetailModal.tsx`
- Modify: `frontend/app/components/events/DiscordLogSection.tsx` (make rows clickable)

**What:** Click an activity log entry to see full details in a modal.

**Step 1:** Create `DiscordLogDetailModal` component:
```tsx
interface DiscordLogDetailModalProps {
  log: DiscordLogEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  repeaterName?: string;
}
```

**Compact section (always visible):**
- Status badge (Success/Failed)
- Action + target type
- Timestamp (absolute + relative)
- Discord message ID (link)
- Repeater name if event has event_repeater
- HTTP status code

**Expandable raw data (Collapsible):**
- `response_data` JSON block
- `error_message` if present
- Log entry PK

**Step 2:** The backend already returns `response_data`, `status_code`, `error_message` in the discord state endpoint. Verify these fields are included. If not, add them to the serializer response.

**Step 3:** Make activity log entries clickable — `onClick={() => setSelectedLog(entry)}`. Open modal.

**Step 4:** Commit.

```
git commit -m "feat: add Discord log detail modal with raw data view"
```

---

## Task 6: Lifecycle Test Extension

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/06-full-lifecycle.spec.ts`

**What:** After the lifecycle test creates events, verify the task schedule UI.

**Step 1:** After step 13 (navigate to event page), add:

```typescript
// 14. Verify Task Schedule on Discord tab
await page.getByTestId('event-tab-discord').click();
await expect(page.getByText('Task Schedule')).toBeVisible({ timeout: 5000 });
await page.getByText('Task Schedule').click();

// Should show task entries
await expect(page.getByText('Discord Announcement').first()).toBeVisible({ timeout: 5000 });
await expect(page.getByText('Signup Reminder').first()).toBeVisible({ timeout: 5000 });
```

**Step 2:** Run lifecycle test to verify.

**Step 3:** Commit.

```
git commit -m "test: verify task schedule UI in lifecycle E2E test"
```

---

## Task Order

| Task | Depends On | Effort |
|------|-----------|--------|
| 1. Org timezone edit | None | Small |
| 2. Events page repeater tab | None | Medium |
| 3. Task schedule endpoint | None | Medium |
| 4. Task schedule UI | Task 3 | Medium |
| 5. Discord log detail modal | None | Medium |
| 6. Lifecycle test | Tasks 3, 4 | Small |

Tasks 1, 2, 3, 5 are independent — can be done in parallel or any order.
Task 4 requires Task 3. Task 6 requires Tasks 3+4.
