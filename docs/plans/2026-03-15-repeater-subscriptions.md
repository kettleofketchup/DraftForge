# Repeater Subscriptions & Reminder Hours Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to subscribe to event repeaters for new event/cancellation notifications. Add configurable hours-before for profile reminder and confirm attendance. Mail icon for subscribe toggle.

**Architecture:** New `RepeaterSubscription` model linking user to repeater. Website subscription via API toggle. Subscribe/unsubscribe via mutation hook. Cache invalidation via cacheops `invalidate_obj`. Two new hours fields on `DiscordEventConfigMixin` for profile reminder and confirm attendance timing. Dropdown selectors for hour values.

**Tech Stack:** Django, Django REST Framework, cacheops, React, TanStack Query, TypeScript, Zod

---

### Task 1: Add `discord_profile_reminder_hours` and `discord_confirm_attendance_hours` fields

**Files:**
- Modify: `backend/events/models.py` — add 2 IntegerFields to `DiscordEventConfigMixin`
- Modify: `backend/events/serializers.py` — add to both serializers
- Modify: `frontend/app/components/api/eventsAPI.ts` — add to `EventRepeaterType`
- Modify: `frontend/app/components/events/schemas.ts` — add to `eventSchema`, `discordConfigSchema`, `DISCORD_CONFIG_DEFAULTS`
- Modify: `frontend/app/components/events/DiscordConfigSection.tsx` — add dropdown selectors
- Modify: `frontend/app/components/events/EditEventModal.tsx` — add to reset
- Modify: `frontend/app/components/events/EditRepeaterModal.tsx` — add to reset

**Step 1: Backend model fields**

Add to `DiscordEventConfigMixin` after `discord_profile_reminder`:

```python
discord_profile_reminder_hours = models.IntegerField(
    default=24,
    help_text="Hours before event to send profile update reminder",
)
```

Add after `discord_confirm_attendance`:

```python
discord_confirm_attendance_hours = models.IntegerField(
    default=2,
    help_text="Hours before event to send attendance confirmation request",
)
```

**Step 2:** Add both to `EventRepeaterSerializer.Meta.fields` and `EventSerializer.Meta.fields`.

**Step 3:** Add to `EventRepeaterType` interface, `eventSchema`, `discordConfigSchema`, `DISCORD_CONFIG_DEFAULTS`.

**Step 4:** Add dropdown selectors in `DiscordConfigSection`. Show when the parent boolean is enabled. Use a `Select` with predefined hour options: `[1, 2, 4, 6, 12, 24, 48]`.

```tsx
const REMINDER_HOURS_OPTIONS = [
  { value: 1, label: '1 hour before' },
  { value: 2, label: '2 hours before' },
  { value: 4, label: '4 hours before' },
  { value: 6, label: '6 hours before' },
  { value: 12, label: '12 hours before' },
  { value: 24, label: '1 day before' },
  { value: 48, label: '2 days before' },
];
```

**Step 5:** Add to edit modal `form.reset()` calls.

**Step 6:** Run `just py::manage makemigrations events` then `just py::manage check`.

---

### Task 2: New `RepeaterSubscription` model + CACHEOPS registration

**Files:**
- Modify: `backend/events/models.py`
- Modify: `backend/backend/settings.py` — add CACHEOPS entry

Add after `EventSignup` class:

```python
class RepeaterSubscription(models.Model):
    """User subscription to an event repeater for new event notifications."""

    event_repeater = models.ForeignKey(
        EventRepeater,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="repeater_subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_repeater", "user"],
                name="unique_repeater_user_subscription",
            ),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} → {self.event_repeater.name}"
```

Add to `CACHEOPS` in `settings.py`:

```python
"events.repeatersubscription": {"ops": "all", "timeout": 60 * 60},
```

Run `just py::manage makemigrations events` then `just py::manage check`.

---

### Task 3: Serializer + API endpoints with cache invalidation

**Files:**
- Modify: `backend/events/serializers.py`
- Modify: `backend/events/views.py`

**Step 1:** Add annotated fields to `EventRepeaterSerializer`:

```python
subscriber_count = serializers.IntegerField(read_only=True, default=0)
is_subscribed = serializers.BooleanField(read_only=True, default=False)
```

Add both to `Meta.fields` and `Meta.read_only_fields`.

**Step 2:** Add imports to `views.py`:

```python
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from rest_framework.exceptions import PermissionDenied
from cacheops import invalidate_obj
from events.models import RepeaterSubscription
```

Note: `Count` and `Q` are already imported. Add `BooleanField`, `Exists`, `OuterRef`, `Value` to the existing import line. Add `RepeaterSubscription` to the events.models import.

**Step 3:** Update `EventRepeaterViewSet.get_queryset()` — add annotations BEFORE existing org_id filter:

```python
def get_queryset(self):
    qs = EventRepeater.objects.select_related(
        "organization", "tournament_league", "created_by"
    ).annotate(
        subscriber_count=Count("subscriptions"),
    )
    if self.request.user.is_authenticated:
        qs = qs.annotate(
            is_subscribed=Exists(
                RepeaterSubscription.objects.filter(
                    event_repeater=OuterRef("pk"),
                    user=self.request.user,
                )
            )
        )
    else:
        qs = qs.annotate(is_subscribed=Value(False, output_field=BooleanField()))
    org_id = self.request.query_params.get("organization")
    if org_id:
        qs = qs.filter(organization_id=org_id)
    return qs
```

**Step 4:** Add subscribe/unsubscribe actions WITH `invalidate_obj`:

```python
@action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
def subscribe(self, request, pk=None):
    """Subscribe to event notifications for this repeater.
    Any authenticated user can subscribe (not limited to org staff).
    """
    repeater = self.get_object()
    _, created = RepeaterSubscription.objects.get_or_create(
        event_repeater=repeater, user=request.user
    )
    if created:
        invalidate_obj(repeater)
        return Response({"detail": "Subscribed"}, status=status.HTTP_201_CREATED)
    return Response({"detail": "Already subscribed"}, status=status.HTTP_200_OK)

@action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
def unsubscribe(self, request, pk=None):
    """Unsubscribe from event notifications for this repeater."""
    repeater = self.get_object()
    deleted, _ = RepeaterSubscription.objects.filter(
        event_repeater=repeater, user=request.user
    ).delete()
    if deleted:
        invalidate_obj(repeater)
    return Response({"detail": "Unsubscribed"}, status=status.HTTP_200_OK)
```

---

### Task 4: Frontend — API functions, types, mutation hook

**Files:**
- Modify: `frontend/app/components/api/eventsAPI.ts`
- Modify: `frontend/app/components/api/api.tsx`
- Modify: `frontend/app/hooks/useEvent.ts`

**Step 1:** Add to `EventRepeaterType` interface:

```typescript
subscriber_count: number;
is_subscribed: boolean;
```

**Step 2:** Add API functions:

```typescript
export async function subscribeToRepeater(repeaterId: number): Promise<void> {
  await axios.post(`/events/repeaters/${repeaterId}/subscribe/`);
}

export async function unsubscribeFromRepeater(repeaterId: number): Promise<void> {
  await axios.post(`/events/repeaters/${repeaterId}/unsubscribe/`);
}
```

**Step 3:** Re-export from `api.tsx` barrel.

**Step 4:** Add mutation hook in `useEvent.ts` (follows existing pattern):

```typescript
export function useRepeaterSubscriptionMutation() {
  const queryClient = useQueryClient();
  return {
    subscribe: useMutation({
      mutationFn: (repeaterId: number) => subscribeToRepeater(repeaterId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      },
    }),
    unsubscribe: useMutation({
      mutationFn: (repeaterId: number) => unsubscribeFromRepeater(repeaterId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['event-repeaters'] });
      },
    }),
  };
}
```

---

### Task 5: Frontend — Subscribe button on RepeatersList

**Files:**
- Modify: `frontend/app/routes/organization.tsx`

**Imports needed:**

```typescript
import { Mail, MailCheck } from 'lucide-react';
import { cn } from '~/lib/utils';
import { toast } from 'sonner';
import { useRepeaterSubscriptionMutation } from '~/hooks/useEvent';
```

Note: `Button`, `Tooltip*`, `useQueryClient` are already imported from earlier fixes.

**Step 1:** Update `RepeatersList` — use `useUserStore` directly instead of prop-threading:

```typescript
function RepeatersList({ repeaters, loading, onEdit }: { ... }) {
  const currentUser = useUserStore((state) => state.currentUser);
  const { subscribe, unsubscribe } = useRepeaterSubscriptionMutation();
  const isPending = subscribe.isPending || unsubscribe.isPending;
```

**Step 2:** Add subscribe toggle button using `Mail`/`MailCheck` icons with `text-interactive` active color:

```tsx
{currentUser && (
  <Tooltip>
    <TooltipTrigger asChild>
      <Button
        variant="ghost"
        size="icon"
        className={cn("h-8 w-8", r.is_subscribed && "text-interactive")}
        disabled={isPending}
        onClick={() => {
          if (r.is_subscribed) {
            unsubscribe.mutate(r.id, {
              onError: () => toast.error('Failed to unsubscribe'),
            });
          } else {
            subscribe.mutate(r.id, {
              onSuccess: () => toast.success('Subscribed to notifications'),
              onError: () => toast.error('Failed to subscribe'),
            });
          }
        }}
      >
        {r.is_subscribed ? <MailCheck className="h-3.5 w-3.5" /> : <Mail className="h-3.5 w-3.5" />}
      </Button>
    </TooltipTrigger>
    <TooltipContent>
      {r.is_subscribed ? 'Unsubscribe from notifications' : 'Get notified about new events'}
    </TooltipContent>
  </Tooltip>
)}
```

**Step 3:** Show subscriber count in the metadata line (not action area):

```tsx
<p className="text-sm text-muted-foreground">
  {FREQUENCY_LABELS[r.frequency] ?? r.frequency}
  {r.day_of_week != null && ` on ${DAY_LABELS[r.day_of_week]}`}
  {' at '}
  {r.time_of_day.slice(0, 5)}
  {r.subscriber_count > 0 && (
    <span className="ml-2 text-xs">· {r.subscriber_count} subscribed</span>
  )}
</p>
```

**Step 4:** Hide subscribe button when `discord_notify_new_events` is `false`:

```tsx
{currentUser && r.discord_notify_new_events && (
  // subscribe button...
)}
```

---

### Task 6: Verification

**Step 1:** `just py::manage check`
**Step 2:** `just py::manage makemigrations --check` — no new migrations needed
**Step 3:** `npx tsc --noEmit` — no new errors in events components
**Step 4:** Manual test: subscribe/unsubscribe, verify cache invalidation works

---

## Files Summary

| File | Change |
|------|--------|
| `backend/events/models.py` | Add 2 reminder hours fields + `RepeaterSubscription` model |
| `backend/events/migrations/0009_*.py` | Auto-generated (hours fields + subscription model) |
| `backend/backend/settings.py` | Add `events.repeatersubscription` to CACHEOPS |
| `backend/events/serializers.py` | Add hours fields + `subscriber_count`/`is_subscribed` to repeater serializer |
| `backend/events/views.py` | Annotated queryset + subscribe/unsubscribe actions with `invalidate_obj` |
| `frontend/app/components/api/eventsAPI.ts` | Add subscribe/unsubscribe functions + type fields |
| `frontend/app/components/api/api.tsx` | Re-export new functions |
| `frontend/app/components/events/schemas.ts` | Add hours fields to schemas + defaults |
| `frontend/app/components/events/DiscordConfigSection.tsx` | Add hours dropdown selectors |
| `frontend/app/components/events/EditEventModal.tsx` | Add hours to reset |
| `frontend/app/components/events/EditRepeaterModal.tsx` | Add hours to reset |
| `frontend/app/hooks/useEvent.ts` | Add `useRepeaterSubscriptionMutation` hook |
| `frontend/app/routes/organization.tsx` | Subscribe button with Mail icon, subscriber count |

## Future Work (not in this plan)

- Discord reaction-based subscription (mail emoji on event embed → creates RepeaterSubscription)
- DM notification logic when events are created/cancelled (hook in `generate_events_for_repeater` after event creation loop, and in `EventViewSet.cancel`)
- Subscriber list view for org admins
