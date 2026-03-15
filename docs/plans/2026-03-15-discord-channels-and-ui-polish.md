# Discord Channels & UI Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Discord channel picker for event signup posts and pre-day announcements, plus UI polish (tab icon, field renames, new "mark as interested" toggle).

**Architecture:** New backend endpoint fetches text channels from Discord API via bot token, cached in Redis by org's `discord_server_id`. Two new opt-in channel features on events/repeaters (signup post + announcement), each with boolean toggle + channel ID. Frontend gets a reusable `DiscordChannelPicker` component with search and refresh. Small UI tweaks to existing Discord tab.

**Tech Stack:** Django REST Framework, Redis cache, Discord REST API v10, React, TypeScript, Zod, React Hook Form, Shadcn Select/Combobox

---

### Task 1: Backend — Discord channels endpoint

**Files:**
- Create: `backend/discordbot/services/channels.py`
- Modify: `backend/discordbot/urls.py`

**Step 1: Create `channels.py`**

```python
"""Discord channel listing with Redis caching."""
import logging

import requests
from django.cache import cache
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import Organization
from app.permissions_org import has_org_staff_access

log = logging.getLogger(__name__)

CHANNELS_CACHE_TTL = 600  # 10 minutes


def _fetch_guild_channels(guild_id):
    """Fetch text channels from Discord API for a guild."""
    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/channels"
    headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    # Type 0 = text channel, Type 5 = announcement channel
    return [
        {"id": ch["id"], "name": ch["name"], "type": ch["type"]}
        for ch in response.json()
        if ch["type"] in (0, 5)
    ]


def _get_channels_cached(guild_id):
    """Get channels with Redis cache."""
    cache_key = f"discord_channels_{guild_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    channels = _fetch_guild_channels(guild_id)
    cache.set(cache_key, channels, timeout=CHANNELS_CACHE_TTL)
    return channels


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_discord_channels(request, pk):
    """List text channels for an organization's Discord server.

    GET /api/discord/organizations/<pk>/channels/
    Query params:
        refresh=true — bust cache and re-fetch from Discord
    """
    try:
        org = Organization.objects.get(pk=pk)
    except Organization.DoesNotExist:
        return Response({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return Response({"error": "Permission denied"}, status=403)

    if not org.discord_server_id:
        return Response(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Force refresh if requested
    if request.query_params.get("refresh") == "true":
        cache_key = f"discord_channels_{org.discord_server_id}"
        cache.delete(cache_key)

    try:
        channels = _get_channels_cached(org.discord_server_id)
    except Exception as e:
        log.error(f"Failed to fetch Discord channels for org {org.pk}: {e}")
        return Response(
            {"error": "Failed to fetch Discord channels"}, status=502
        )

    return Response({"channels": channels})
```

**Step 2: Add URL to `discordbot/urls.py`**

Add import and path:

```python
from .services.channels import get_discord_channels

# Add to urlpatterns:
path(
    "organizations/<int:pk>/channels/",
    get_discord_channels,
    name="discord-channels",
),
```

**Step 3: Verify**

```bash
just py::manage check
```

---

### Task 2: Migration — new channel fields on Event and EventRepeater

**Files:**
- Modify: `backend/events/models.py` — add 4 fields to `DiscordEventConfigMixin`, 2 to `EventRepeater`
- Create: migration `0006` via `makemigrations`

**Step 1: Add fields to `DiscordEventConfigMixin` in `models.py`**

Add after `discord_profile_reminder`:

```python
discord_mark_interested = models.BooleanField(
    default=False,
    help_text="Mark signups as 'interested' on the Discord scheduled event",
)
discord_post_signups = models.BooleanField(
    default=False,
    help_text="Post an event embed to a channel for reaction-based signups",
)
discord_post_signups_channel_id = models.CharField(
    max_length=20,
    blank=True,
    default="",
    help_text="Discord channel ID to post signup embed in",
)
discord_announcement = models.BooleanField(
    default=False,
    help_text="Post a pre-day announcement in a channel",
)
discord_announcement_channel_id = models.CharField(
    max_length=20,
    blank=True,
    default="",
    help_text="Discord channel ID for pre-day announcement",
)
discord_announcement_hours = models.IntegerField(
    default=24,
    help_text="Hours before event to post announcement",
)
```

**Step 2: Run makemigrations**

```bash
just py::manage makemigrations events
```

Expected: creates `0006_*.py`

**Step 3: Verify**

```bash
just py::manage check
just py::manage makemigrations --check
```

---

### Task 3: Backend — wire new fields through serializers and services

**Files:**
- Modify: `backend/events/serializers.py`
- Modify: `backend/events/services.py` (no code change needed — `DISCORD_CONFIG_FIELDS` is auto-derived from mixin)

**Step 1: Add fields to `EventRepeaterSerializer.Meta.fields`**

Add after `discord_profile_reminder`:

```python
"discord_mark_interested",
"discord_post_signups",
"discord_post_signups_channel_id",
"discord_announcement",
"discord_announcement_channel_id",
"discord_announcement_hours",
```

**Step 2: Add fields to `EventSerializer.Meta.fields`**

Same 6 fields after `discord_profile_reminder`.

**Step 3: Verify services auto-picks up new fields**

`DISCORD_CONFIG_FIELDS` uses `DiscordEventConfigMixin._meta.get_fields()` — the new mixin fields are automatically included. No changes needed in `services.py`.

```bash
just py::manage check
```

---

### Task 4: Frontend — API types and Zod schemas

**Files:**
- Modify: `frontend/app/components/api/eventsAPI.ts`
- Modify: `frontend/app/components/events/schemas.ts`

**Step 1: Add to `EventRepeaterType` interface (eventsAPI.ts)**

After `discord_profile_reminder`:

```typescript
discord_mark_interested: boolean;
discord_post_signups: boolean;
discord_post_signups_channel_id: string;
discord_announcement: boolean;
discord_announcement_channel_id: string;
discord_announcement_hours: number;
```

**Step 2: Add Discord channels API function (eventsAPI.ts)**

```typescript
export interface DiscordChannel {
  id: string;
  name: string;
  type: number;
}

export async function getDiscordChannels(
  orgId: number,
  refresh = false
): Promise<DiscordChannel[]> {
  const params = refresh ? '?refresh=true' : '';
  const { data } = await axios.get<{ channels: DiscordChannel[] }>(
    `/discord/organizations/${orgId}/channels/${params}`
  );
  return data.channels;
}
```

**Step 3: Add to `eventSchema` (schemas.ts)**

After `discord_profile_reminder`:

```typescript
discord_mark_interested: z.boolean(),
discord_post_signups: z.boolean(),
discord_post_signups_channel_id: z.string(),
discord_announcement: z.boolean(),
discord_announcement_channel_id: z.string(),
discord_announcement_hours: z.number(),
```

**Step 4: Add to `createEventInputSchema` (schemas.ts)**

Same 6 fields in the discord config section.

**Step 5: Re-export from `api.tsx` barrel**

Add `getDiscordChannels` and `DiscordChannel` type to the events re-export block.

**Step 6: Verify**

```bash
cd frontend && npx tsc --noEmit
```

---

### Task 5: Frontend — `DiscordChannelPicker` component

**Files:**
- Create: `frontend/app/components/events/DiscordChannelPicker.tsx`

Reusable component that fetches + displays org's Discord channels in a Select with a refresh button.

```tsx
import { RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { getDiscordChannels, type DiscordChannel } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

interface DiscordChannelPickerProps {
  organizationId: number;
  value: string;
  onChange: (channelId: string) => void;
  disabled?: boolean;
}

export function DiscordChannelPicker({
  organizationId,
  value,
  onChange,
  disabled,
}: DiscordChannelPickerProps) {
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChannels = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await getDiscordChannels(organizationId, refresh);
        setChannels(result);
      } catch {
        setError('Failed to load channels');
      } finally {
        setLoading(false);
      }
    },
    [organizationId]
  );

  useEffect(() => {
    if (organizationId) fetchChannels();
  }, [organizationId, fetchChannels]);

  return (
    <div className="flex items-center gap-2">
      <Select
        value={value}
        onValueChange={onChange}
        disabled={disabled || loading}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder={loading ? 'Loading...' : 'Select channel'} />
        </SelectTrigger>
        <SelectContent>
          {error && (
            <div className="px-2 py-1.5 text-sm text-error">{error}</div>
          )}
          {channels.map((ch) => (
            <SelectItem key={ch.id} value={ch.id}>
              # {ch.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0"
        onClick={() => fetchChannels(true)}
        disabled={loading}
        title="Refresh channels"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
      </Button>
    </div>
  );
}
```

---

### Task 6: Frontend — Update `DiscordConfigSection` with new fields and UI polish

**Files:**
- Modify: `frontend/app/components/events/DiscordConfigSection.tsx`

**Changes:**
1. Add Discord icon to export (for tab usage in modals)
2. Rename "Sync signups" → "Synchronize signups" with updated description: "Keep website and Discord event signups in sync"
3. Add "Mark signups as interested" checkbox after sync signups (inside `createEvent` conditional)
4. Add "Post signup embed" section: boolean toggle → channel picker (inside new bordered card)
5. Add "Pre-day announcement" section: boolean toggle → channel picker + hours field (inside new bordered card)
6. Accept `organizationId` prop to pass to channel pickers

**Props change:**

```typescript
interface DiscordConfigSectionProps {
  control: Control<any>;
  watch: UseFormWatch<any>;
  isRepeater: boolean;
  organizationId: number;
}
```

**New fields layout (appended after existing cards):**

```
┌─────────────────────────────────────────┐
│ ☐ Post event signup embed               │
│   Channel: [# general     ▾] [↻]       │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ ☐ Pre-day announcement                 │
│   Channel: [# announcements ▾] [↻]     │
│   Hours before: [24]                    │
└─────────────────────────────────────────┘
```

---

### Task 7: Frontend — Update all three modals

**Files:**
- Modify: `frontend/app/components/events/CreateEventModal.tsx`
- Modify: `frontend/app/components/events/EditEventModal.tsx`
- Modify: `frontend/app/components/events/EditRepeaterModal.tsx`

**Changes for each modal:**

1. **Discord icon in tab** — Import the Discord SVG icon and add to the Discord tab trigger:

```tsx
<TabsTrigger value="discord">
  <DiscordIcon className="h-4 w-4" />
  Discord
</TabsTrigger>
```

Export `DiscordIcon` from `DiscordConfigSection.tsx` so all modals can use it.

2. **Add default values** for the 6 new fields:

```typescript
discord_mark_interested: false,
discord_post_signups: false,
discord_post_signups_channel_id: '',
discord_announcement: false,
discord_announcement_channel_id: '',
discord_announcement_hours: 24,
```

3. **Add to Zod schemas** (edit modals have local schemas):

```typescript
discord_mark_interested: z.boolean(),
discord_post_signups: z.boolean(),
discord_post_signups_channel_id: z.string(),
discord_announcement: z.boolean(),
discord_announcement_channel_id: z.string(),
discord_announcement_hours: z.number().int().min(1),
```

4. **Add to reset** (edit modals populate from existing data)

5. **Pass `organizationId`** to `<DiscordConfigSection>`:
   - CreateEventModal: already has `organizationId` prop
   - EditEventModal: get from `event.organization`
   - EditRepeaterModal: get from `repeater.organization`

---

### Task 8: Verification

**Step 1: Django checks**

```bash
just py::manage check
just py::manage makemigrations --check
```

**Step 2: TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Migrate test DB**

```bash
just db::migrate::test
```

---

## Files Summary

| File | Change |
|------|--------|
| `backend/discordbot/services/channels.py` | New: channels endpoint with Redis cache |
| `backend/discordbot/urls.py` | Add channels URL |
| `backend/events/models.py` | Add 6 fields to `DiscordEventConfigMixin` |
| `backend/events/migrations/0006_*.py` | Auto-generated migration |
| `backend/events/serializers.py` | Add 6 fields to both serializers |
| `frontend/app/components/api/eventsAPI.ts` | Add channel types/API + 6 fields to `EventRepeaterType` |
| `frontend/app/components/events/schemas.ts` | Add 6 fields to Zod schemas |
| `frontend/app/components/events/DiscordChannelPicker.tsx` | New: reusable channel picker with refresh |
| `frontend/app/components/events/DiscordConfigSection.tsx` | Add new fields, export `DiscordIcon`, accept `organizationId` |
| `frontend/app/components/events/CreateEventModal.tsx` | Discord icon in tab, new defaults, pass orgId |
| `frontend/app/components/events/EditEventModal.tsx` | Discord icon in tab, new fields/defaults, pass orgId |
| `frontend/app/components/events/EditRepeaterModal.tsx` | Discord icon in tab, new fields/defaults, pass orgId |
| `frontend/app/components/api/api.tsx` | Re-export `getDiscordChannels`, `DiscordChannel` |
