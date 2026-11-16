# User Avatar & Display Name Patterns

**ALWAYS use these helpers** - never use raw avatar URLs or hand-rolled `discordNickname || username` chains.

## Import & Usage

```typescript
import { UserAvatar } from "~/components/user/UserAvatar";
import { useDisplayName } from "~/hooks/useDisplayName";
import { useDisplayOrgId } from "~/hooks/useDisplayOrgId";

const name = useDisplayName(user, useDisplayOrgId());

<UserAvatar user={user} size="md" />
<span>{name}</span>
```

## Display Names

Names come from Discord; there is no site nickname. The chain depends on context:

1. **Org page** (`orgId` given): server nickname in that org (`UserEntry.orgNicknames[orgId]`) → `discordNickname` (global display name) → `username` → `User <pk>`
2. **No org** (`orgId` null): `discordNickname` → `username` → `User <pk>`
3. **GuildMember** (raw Discord member): `nick` → `global_name` → `username`
4. **No object / no pk**: `'?'`

Blank values are skipped. Pick the helper by where you are:

```typescript
// Component: reactive, re-renders when a synced name lands in the store
const name = useDisplayName(userOrPk, useDisplayOrgId(), { maxLength: 20 });

// Non-reactive (callbacks, toasts, legacy call sites)
import { DisplayName } from "~/components/user/avatar";
DisplayName(user);              // global chain
DisplayName(user, 20, orgId);   // org chain, truncated

// Pure code / only an id
import { resolveDisplayName, displayNameById } from "~/lib/userDisplayName";
resolveDisplayName(user, { orgId });
displayNameById(pk, payload.username, orgId);
```

`useDisplayName` requires `orgId: number | null`. Get it from `useDisplayOrgId()` (route `DisplayOrgContext`), never from `orgStore.currentOrg`.

```typescript
// ❌ WRONG - skips the server nickname and drifts
{user.discordNickname || user.username}
{captain?.username || 'Unknown'}

// ✅ CORRECT - hooks at the top of the component
const orgId = useDisplayOrgId();
const name = useDisplayName(user, orgId);
{name}
```

## Converting Non-UserType Objects

Include `avatar` and `discordId` when available - they're needed for Discord CDN URLs:

```typescript
const toUser = (data: {
  pk: number;
  username: string;
  discordNickname?: string | null;
  avatar?: string | null;
  avatarUrl?: string | null;  // Full Discord CDN URL (preferred)
  discordId?: string | null;  // Needed to construct CDN URL from hash
}) => ({
  pk: data.pk,
  username: data.username,
  discordNickname: data.discordNickname ?? null,
  avatar: data.avatar ?? null,
  avatarUrl: data.avatarUrl ?? undefined,
  discordId: data.discordId ?? undefined,
});

<UserAvatar user={toUser(captain)} size="sm" />
```

## What AvatarUrl Handles (Priority Order)

1. Returns `avatarUrl` if available (full Discord CDN URL)
2. Returns `avatar` if it starts with `http` (already a URL)
3. Constructs Discord CDN URL if `discordId` + `avatar` hash exist
4. Generates ui-avatars.com fallback from `discordNickname`/`username`

## Wrong vs Correct

```typescript
// ❌ WRONG - avatar may be Discord hash like "c9d2fe164ad4d0022bd7afbb00ef2a64"
<img src={user.avatar || "/default.png"} />

// ✅ CORRECT
<UserAvatar user={user} size="sm" />
```
