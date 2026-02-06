# AddUserModal — Standard Reusable Component

**Issue**: [#108 — Frontend AddUserModal Standard](https://github.com/kettleofketchup/DraftForge/issues/108)
**Date**: 2026-02-05

## Overview

A reusable modal for adding users to Orgs, Tournaments, and Leagues. Single search bar triggers two parallel backend searches — site users and Discord members. The modal is entity-agnostic; the parent provides callbacks and context.

## Architecture

### Component API

```tsx
<AddUserModal
  open={open}
  onOpenChange={setOpen}
  title="Add Member to Season 5 League"
  entityContext={{
    orgId: useOrgStore.getState().currentOrg?.pk,
    leagueId: useLeagueStore.getState().currentLeague?.pk,
  }}
  onAdd={(user: UserType) => Promise<void>}
  isAdded={(user: UserType) => boolean}
  entityLabel="Season 5 League"
/>
```

- `onAdd` — parent handles the API call (add to org, league, or tournament)
- `isAdded` — parent checks its own membership state; returns true if user is already a member
- `entityContext` — passed to backend search for membership annotation (not filtering)
- `entityLabel` — displayed in "Already in {label}" gray text

### Search Flow

Single search bar (debounced 300ms, min 3 characters) fires two parallel API calls:

```
User types "john"
  -> GET /api/search-users/?q=john&org_id=5&league_id=12     -> Site Users column
  -> GET /api/discord/search-discord-members/?q=john&org_id=5 -> Discord Members column
```

Both return max 20 results. Results render into their respective columns.

## Layout

### Desktop (>=768px) — Two Columns

```
+-----------------------------------+------------------------------------+
|  Site Users                       |  Discord Members                   |
|                                   |                                    |
|  +-----------------------------+  |  +------------------------------+  |
|  | Search username/nick/steam  |  |  | (shared search bar above)    |  |
|  +-----------------------------+  |  +------------------------------+  |
|                                   |  [       Refresh Discord        ]  |
|  +-----------------------------+  |                                    |
|  | UserStrip  "Org Member" [+] |  |  +------------------------------+  |
|  | UserStrip  "Already in      |  |  | DiscordUser             [+]  |  |
|  |            League" (grayed) |  |  | DiscordUser  "Already in     |  |
|  | UserStrip  (global)     [+] |  |  |              League" (grayed)|  |
|  | UserStrip  "Other Org:      |  |  | DiscordUser  (no account)[+] |  |
|  |            Team X"      [+] |  |  +------------------------------+  |
|  +-----------------------------+  |                                    |
+-----------------------------------+------------------------------------+
```

### Mobile (<768px) — Tabbed

Two tabs: `[Site Users]` `[Discord]`. Same content stacked vertically within each tab.

### Result States

**Site Users:**
- Already added: grayed out, "Already in {entityLabel}", no Add button
- Membership badge in contextSlot: "League Member", "Org Member", "Other Org: {name}", or blank (global)

**Discord Members:**
- Has site account + already added: grayed out, "Already in {entityLabel}"
- Has site account + not added: normal, Add button
- No site account: normal, Add button (auto-creates user on click via `createFromDiscordData`)
- No Discord server configured for org: column shows "No Discord server configured" message

## Backend Changes

### 1. Enhanced `GET /api/search-users/`

**Current**: searches `discordUsername`, `discordNickname`, `guildNickname`, `username`. Returns max 20 results.

**Changes:**
- Add `steamid` and `steam_account_id` to searchable fields
- Accept optional query params: `org_id`, `league_id`
- Annotate each result with `membership` and `membership_label`:
  - `"league"` + league name — user is in the provided league
  - `"org"` + org name — user is in the provided org but not the league
  - `"other_org"` + org name — user is in a different org
  - `null` — global user, no org membership
- Permission: `IsAuthenticated` (unchanged)

**Response:**

```json
{
  "results": [
    {
      "pk": 42,
      "username": "john123",
      "nickname": "Johnny",
      "avatar": "...",
      "avatarUrl": "...",
      "steamid": 76561198000000000,
      "mmr": 3500,
      "membership": "league",
      "membership_label": "Season 5 League"
    },
    {
      "pk": 88,
      "username": "johndoe",
      "nickname": null,
      "avatar": "...",
      "avatarUrl": "...",
      "steamid": null,
      "mmr": 2800,
      "membership": "other_org",
      "membership_label": "Team Liquid"
    }
  ]
}
```

### 2. New `GET /api/discord/search-discord-members/`

```
GET /api/discord/search-discord-members/?q=john&org_id=5
```

- Permission: `IsAuthenticated` + org staff access
- Looks up org's `discord_server_id`
- Checks Redis for `discord_members:{discord_server_id}`
  - Cache miss: fetches from Discord API via `get_discord_members_data(guild_id)`, stores in Redis with 1-hour TTL
  - Cache hit: filters cached list server-side
- Searches against `user.username`, `user.global_name`, `nick`
- Cross-references `user.id` against `CustomUser.discordId` to annotate `has_site_account`
- Returns max 20 results

**Response:**

```json
{
  "results": [
    {
      "user": {
        "id": "123456789",
        "username": "johndiscord",
        "global_name": "John",
        "avatar": "abc123"
      },
      "nick": "JohnnyD",
      "has_site_account": true,
      "site_user_pk": 42
    },
    {
      "user": {
        "id": "987654321",
        "username": "johnother",
        "global_name": "John O",
        "avatar": null
      },
      "nick": null,
      "has_site_account": false,
      "site_user_pk": null
    }
  ]
}
```

### 3. New `POST /api/discord/refresh-discord-members/`

```
POST /api/discord/refresh-discord-members/?org_id=5
```

- Permission: `IsAuthenticated` + org staff access
- Purges Redis key `discord_members:{discord_server_id}`
- Re-fetches from Discord API, stores in Redis (1-hour TTL)
- Returns `{ "count": 2000, "refreshed": true }`

### 4. New "Add Member" Endpoints

These don't exist yet. Each accepts `{ "user_id": int }` or `{ "discord_data": object }` (for auto-create).

**`POST /api/organizations/{orgId}/members/`**
- Creates `OrgUser` record
- Permission: org admin/staff access
- Returns created user

**`POST /api/leagues/{leagueId}/members/`**
- Creates `LeagueUser` (and `OrgUser` if user isn't in the parent org yet)
- Permission: league admin/staff access
- Returns created user

**`POST /api/tournaments/{tournamentId}/members/`**
- Adds user to `tournament.users` M2M
- Permission: tournament admin/staff access (via league/org)
- Returns created user

Auto-create flow for Discord members without site accounts:
1. Backend receives `{ "discord_data": { "id": "...", "username": "...", ... } }`
2. Calls `CustomUser.createFromDiscordData(discord_data)` (existing method)
3. Creates the membership record (OrgUser/LeagueUser/tournament M2M)
4. Returns the new user

## Frontend Changes

### New Files

```
frontend/app/components/shared/AddUserModal/
  AddUserModal.tsx          -- main modal, layout, single search bar
  SiteUserResults.tsx       -- left column, renders site user search results
  DiscordMemberResults.tsx  -- right column, renders discord search results
  DiscordMemberStrip.tsx    -- display component for a discord member row
  types.ts                  -- EntityContext, MembershipAnnotation, SearchResult types
```

### New API Functions

```
frontend/app/components/api/
  orgAPI.tsx    -- add: searchDiscordMembers(orgId, query), refreshDiscordMembers(orgId)
  api.tsx       -- update: searchUsers(query, orgId?, leagueId?) — enhanced
  orgAPI.tsx    -- add: addOrgMember(orgId, payload)
  leagueAPI.tsx -- add: addLeagueMember(leagueId, payload)
  tournamentAPI.tsx -- add: addTournamentMember(tournamentId, payload)
```

### Component Details

**AddUserModal.tsx**
- Uses `FormDialog` shell (close button only, no form submission)
- Single search input at the top
- Desktop: two-column grid. Mobile: tab switcher (`Site Users` | `Discord`)
- Manages search state, debounce, parallel fetch calls
- Passes results down to `SiteUserResults` and `DiscordMemberResults`

**SiteUserResults.tsx**
- Renders list of `UserStrip` components
- `contextSlot`: membership badge (League Member / Org Member / Other Org: {name})
- `actionSlot`: Add button, or grayed "Already in {entityLabel}" via `isAdded` callback

**DiscordMemberResults.tsx**
- Refresh Discord button at top
- Renders list of `DiscordMemberStrip` components
- Add button calls `onAdd` with either `{ user_id }` (has account) or `{ discord_data }` (auto-create)
- Grayed out if `has_site_account && isAdded(siteUser)`

**DiscordMemberStrip.tsx**
- Lightweight row: Discord avatar + username + global_name + nick
- Similar visual style to `UserStrip` but for Discord data shape

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Both searches return empty | Inline "No results found" message |
| Org has no `discord_server_id` | Discord column shows "No Discord server configured" |
| Refresh fails | Toast error, button stops spinning |
| `onAdd` fails | Toast error with message |
| Duplicate add | Prevented by `isAdded` on frontend, `unique_together` on backend |
| Search < 3 characters | No API calls, show hint text |

## Permissions

| Endpoint | Permission |
|----------|------------|
| `GET /search-users/` | `IsAuthenticated` |
| `GET /search-discord-members/` | `IsAuthenticated` + org staff |
| `POST /refresh-discord-members/` | `IsAuthenticated` + org staff |
| `POST /organizations/{id}/members/` | `IsAuthenticated` + org admin/staff |
| `POST /leagues/{id}/members/` | `IsAuthenticated` + league admin/staff |
| `POST /tournaments/{id}/members/` | `IsAuthenticated` + entity admin/staff |

## Redis Cache Strategy

- Key: `discord_members:{discord_server_id}`
- Value: JSON-serialized list of Discord member objects
- TTL: 1 hour
- Refresh button: purges key, re-fetches, re-stores
- Search endpoint: lazy-loads on cache miss
