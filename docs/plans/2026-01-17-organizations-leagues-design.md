# Organizations, Leagues & Tournament Improvements Design

**Status:** Completed

**Date:** 2026-01-17
**Branch:** `user-captain-pop-over`
**Status:** Draft

## Overview

Add organization and league management to DTX, improving tournament organization and enabling multi-org support. Also modernize tournament creation forms and add profile steam ID editing.

## Goals

1. Create Organization and League models with hierarchical admin permissions
2. Build Organizations and Leagues pages with card/popover UI
3. Add tournament filtering by org/league
4. Modernize tournament create form (Zod, datetime picker, league selector)
5. Enable steam ID editing on profile page

## Data Model

### New Models

**Organization**
```python
class Organization(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    logo = models.URLField(blank=True)
    rules_template = models.TextField(blank=True)  # Markdown, sanitized on save
    admins = models.ManyToManyField('CustomUser', related_name='admin_organizations')
    staff = models.ManyToManyField('CustomUser', related_name='staff_organizations')
    default_league = models.ForeignKey('League', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
```

**League** (1:1 with Steam league)
```python
class League(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='leagues')
    steam_league_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    rules = models.TextField(blank=True)  # Markdown, sanitized on save
    prize_pool = models.CharField(max_length=100, blank=True)
    admins = models.ManyToManyField('CustomUser', related_name='admin_leagues')
    staff = models.ManyToManyField('CustomUser', related_name='staff_leagues')
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### Modified Models

**CustomUser**
- Add `default_organization: FK → Organization (nullable)` - browsing preference

**Tournament**
- Change `league_id` (integer) → `league` (FK → League, nullable for backwards compat)
- `date_played` stays as-is (Django handles timezone)

### Permission Hierarchy

```
Organization Admin → can manage org + ALL leagues under it
Organization Staff → staff access to org + ALL leagues under it
League Admin       → can manage ONLY that specific league
League Staff       → staff access to ONLY that specific league
```

```python
def has_league_admin_access(user, league):
    return (user.is_superuser or
            user in league.organization.admins.all() or
            user in league.admins.all())

def has_league_staff_access(user, league):
    return (has_league_admin_access(user, league) or
            user in league.organization.staff.all() or
            user in league.staff.all())
```

### Markdown Sanitization

Use `nh3` (Rust-based) for backend sanitization on save, and `react-markdown` with `rehype-sanitize` for frontend rendering. Defense in depth.

```python
import nh3

def sanitize_markdown(content: str) -> str:
    """Sanitize markdown to prevent XSS."""
    return nh3.clean(content)

def save(self, *args, **kwargs):
    if self.rules:
        self.rules = sanitize_markdown(self.rules)
    super().save(*args, **kwargs)
```

## API Endpoints

### New Endpoints

**Organizations**
```
GET    /organizations/              - List all orgs
GET    /organizations/{id}/         - Org detail with leagues
POST   /organizations/              - Create org (superuser)
PATCH  /organizations/{id}/         - Update org (org admin)
DELETE /organizations/{id}/         - Delete org (superuser)
```

**Leagues**
```
GET    /leagues/                    - List all leagues (filterable by org)
GET    /leagues/{id}/               - League detail with tournaments
POST   /leagues/                    - Create league (org admin+)
PATCH  /leagues/{id}/               - Update league (league admin+)
DELETE /leagues/{id}/               - Delete league (org admin+)
POST   /leagues/{id}/sync/          - Sync from Steam API (league admin+)
```

### Modified Endpoints

```
GET    /tournaments/                - Add ?org={id}&league={id} filters
                                    - Default sort: most recent first
PATCH  /users/{id}/                 - Allow setting default_organization
```

## Frontend Structure

> **Note to implementor:** Analyze existing `frontend/app/` structure before implementing. Match existing patterns for hooks, components, pages, and API layer. The structure below is a guide - adapt to match what's already there.

### New Components (with co-located hooks and forms)

**`components/organization/`**
- `OrganizationCard.tsx` - Compact card for grid display
- `OrganizationPopover.tsx` - Hover preview (leagues, description)
- `OrganizationSelect.tsx` - Dropdown selector for filters/forms
- `schemas.ts` - Zod schemas
- **`hooks/`**
  - `useOrganizations.ts` - Fetch/cache organizations list
  - `useOrganization.ts` - Fetch single org with leagues
- **`forms/`**
  - `CreateOrganizationModal.tsx` - Zod form modal for creating
  - `EditOrganizationForm.tsx` - Zod form for editing

**`components/league/`**
- `LeagueCard.tsx` - Compact card (name, Steam ID badge, counts)
- `LeaguePopover.tsx` - Hover preview (recent tournaments)
- `LeagueSelect.tsx` - Dropdown selector for filters/forms
- `schemas.ts` - Zod schemas
- **`hooks/`**
  - `useLeagues.ts` - Fetch leagues (with optional org filter)
  - `useLeague.ts` - Fetch single league with tournaments
  - `useLeagueSync.ts` - Trigger Steam sync for league
- **`forms/`**
  - `CreateLeagueModal.tsx` - Zod form modal for creating
  - `EditLeagueForm.tsx` - Zod form for editing

**`components/tournament/`** (modified)
- `TournamentFilterBar.tsx` - Collapsible org/league filter
- **`forms/`**
  - `createModal.tsx` - Refactor to Zod + league picker + datetime picker

### New Pages (route/layout logic)

**`pages/organizations/`**
- `index.tsx` - List page, uses `OrganizationCard` grid
- `$organizationId.tsx` - Detail page, uses `LeagueCard` grid

**`pages/leagues/`**
- `$leagueId.tsx` - Detail page, shows filtered tournaments

### Modified Pages

**`pages/tournaments/`**
- `index.tsx` - Add `TournamentFilterBar`, change sort order to most recent first

**`pages/profile/`**
- `profile.tsx` - Add Steam ID field with conditional Zod validation

### Zustand Store Updates (`store/userStore.ts`)

**New State:**
```typescript
organizations: OrganizationType[]
organization: OrganizationType | null  // selected org
leagues: LeagueType[]
league: LeagueType | null  // selected league
```

**New Actions:**
```typescript
getOrganizations(): Promise<void>
setOrganization(org: OrganizationType): void
getLeagues(orgId?: number): Promise<void>
setLeague(league: LeagueType): void
```

**Modified State:**
```typescript
// tournaments already exists, add filtering support
getTournaments(filters?: { orgId?: number, leagueId?: number }): Promise<void>
```

**Persistence:**
- Add `organizations` and `leagues` to localStorage hydration (like `users`)

## UI Components & Forms

### Zod + React Hook Form Pattern (shadcn/ui)

**Schema example:**
```typescript
import * as z from "zod"

const createLeagueSchema = z.object({
  steam_league_id: z.number().min(1, "Steam League ID is required"),
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  rules: z.string().optional(),
})
```

**Form setup:**
```typescript
import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm } from "react-hook-form"

const form = useForm<z.infer<typeof createLeagueSchema>>({
  resolver: zodResolver(createLeagueSchema),
  defaultValues: {
    steam_league_id: undefined,
    name: "",
    description: "",
    rules: "",
  },
})
```

**Field pattern:**
```tsx
<Controller
  name="name"
  control={form.control}
  render={({ field, fieldState }) => (
    <Field data-invalid={fieldState.invalid}>
      <FieldLabel htmlFor={field.name}>League Name</FieldLabel>
      <Input
        {...field}
        id={field.name}
        aria-invalid={fieldState.invalid}
        placeholder="Enter league name"
      />
      {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
    </Field>
  )}
/>
```

### DateTime Picker (Tournament Create)

- Use `shadcn/ui` date picker + time input
- Display timezone abbreviation next to selected time (e.g., "PST")
- Store as UTC in database
- Show user's local timezone (auto-detected via `Intl.DateTimeFormat`)

```tsx
// Display format example
"January 20, 2026 at 7:00 PM PST"
```

### Collapsible Filter Bar (Tournaments Page)

- Collapsed by default, shows "Filter" button with icon
- Click to expand: reveals Org dropdown → League dropdown (filtered by org)
- "Clear filters" button when any filter active
- Filter state persisted in URL params (`?org=1&league=2`)

### Popovers (Organization & League)

**Trigger:** Hover on card (same pattern as PlayerPopover/CaptainPopover)

**OrganizationPopover content:**
- Logo + name header
- Description snippet (truncated)
- League count, tournament count
- "View Organization →" link

**LeaguePopover content:**
- Name + Steam ID badge
- 2-3 recent/upcoming tournaments (mini list)
- Active match count
- "View League →" link

### Profile Steam ID Field

**Validation:** Frontend-only check - users can't clear an existing steam ID

```typescript
// In component - conditional validation based on existing value
const profileSchema = z.object({
  steamid: z.string().optional(),
  // ... other fields
});

const form = useForm({
  resolver: zodResolver(
    profileSchema.refine(
      (data) => {
        if (existingSteamId && !data.steamid) {
          return false;
        }
        return true;
      },
      { message: "Steam ID cannot be cleared once set", path: ["steamid"] }
    )
  ),
});
```

**UI:** Show info text when field has value: "Steam ID cannot be removed once set"

## Backend Implementation

### Django Migrations

**Migration order:**
1. Create `Organization` model
2. Create `League` model (FK to Organization)
3. Add `default_organization` FK to `CustomUser`
4. Modify `Tournament` - add `league` FK (nullable for backwards compat)

### Steam League Sync

```python
def sync_from_steam(self):
    """Fetch and update league data from Steam API."""
    from app.services.steam import get_league_info

    data = get_league_info(self.steam_league_id)
    if data:
        self.name = data.get('name', self.name)
        self.prize_pool = data.get('prize_pool', '')
        self.last_synced = timezone.now()
        self.save()
```

## Navigation

```
Header Nav:
  Organizations | Tournaments | Profile
              ↓
  Click "Organizations" → /organizations
  Click org → /organizations/{id} (shows leagues)
  Click league → /leagues/{id} (shows tournaments)
```

## Out of Scope

- User membership in organizations (orgs are for browsing/admin only)
- Multiple Steam leagues per League model (1:1 mapping)
- Organization join requests / invite codes
- Public/private organization visibility

## Implementation Notes

- DTX is currently the only organization, but model supports multi-org
- Existing tournaments with `league_id` integer field will need data migration to new `league` FK
- All new forms should use Zod + React Hook Form + shadcn/ui pattern
