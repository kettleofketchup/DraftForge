# User Avatar & Display Name Patterns

**ALWAYS use these helpers** - never use raw avatar URLs or `nickname || username` directly.

## Import & Usage

```typescript
import { AvatarUrl, UserName } from "~/components/user/avatar";

// Avatar - handles Discord CDN, hash construction, and fallbacks
<img src={AvatarUrl(user)} alt={UserName(user)} className="w-10 h-10 rounded-full" />

// Display name - prefers nickname over username
<span>{UserName(user)}</span>
```

## UserName Helper

**ALWAYS use `UserName(user)`** instead of `user.nickname || user.username`:

```typescript
// ❌ WRONG - inconsistent and verbose
{user.nickname || user.username}
{captain?.nickname || captain?.username || 'Unknown'}

// ✅ CORRECT
{UserName(user)}
{captain ? UserName(captain) : 'Unknown'}
```

### What UserName Returns (Priority Order)

1. **GuildMember**: `nick` → `global_name` → `username`
2. **UserType/UserClassType**: `nickname` → `username`
3. **Undefined**: `'?'`

## Converting Non-UserType Objects

Include `avatarUrl` and `discordId` when available - they're needed for Discord CDN URLs:

```typescript
// Convert captain/player data to UserType - include all avatar-related fields!
const toUser = (data: {
  pk: number;
  username: string;
  nickname?: string | null;
  avatar?: string | null;
  avatarUrl?: string | null;  // Full Discord CDN URL (preferred)
  discordId?: string | null;  // Needed to construct CDN URL from hash
}) => ({
  pk: data.pk,
  username: data.username,
  nickname: data.nickname ?? null,
  avatar: data.avatar ?? null,
  avatarUrl: data.avatarUrl ?? undefined,
  discordId: data.discordId ?? undefined,
});

<img src={AvatarUrl(toUser(captain))} />
```

## What It Handles (Priority Order)

1. Returns `avatarUrl` if available (full Discord CDN URL)
2. Returns `avatar` if it starts with `http` (already a URL)
3. Constructs Discord CDN URL if `discordId` + `avatar` hash exist
4. Generates ui-avatars.com fallback from username/nickname

## Wrong vs Correct

```typescript
// ❌ WRONG - avatar may be Discord hash like "c9d2fe164ad4d0022bd7afbb00ef2a64"
<img src={user.avatar || "/default.png"} />

// ✅ CORRECT
<img src={AvatarUrl(user)} />
```
