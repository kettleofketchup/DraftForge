# People in the frontend: names, avatars and search

Every person on screen goes through two helpers. They resolve the user, fill in
what the payload lacks from the user cache, and pick the org from the page.

```tsx
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';

<UserAvatar user={player} size="sm" />
<span>{DisplayName(player)}</span>
toast.success(`${DisplayName(player)} has been removed`);
```

The `draftforge/*` lint rules enforce this (see [Lint rules](#lint-rules)); each
error links to the section below that explains the fix.

## What a name resolves to

`DisplayName(user)` returns the first of:

1. the org server nickname, on a page that belongs to an org
2. the Discord global name (`discordNickname`)
3. the site nickname (for users without a Discord name)
4. the username
5. `User <pk>`, or `?` with no pk

Discord guild members (`{ nick, user: { username, global_name } }`) resolve to
`nick` → `global_name` → `username`.

Never rebuild this chain by hand (`a.nickname || a.username`, `guildNickname ??
…`): it skips the server nickname and the cache.

## Pass the payload as-is

Both helpers accept any user-shaped object. They find the user's id in `pk`,
then `user_id`, then a numeric `user`, then `id` (only on objects carrying user
fields), and merge the cached user: payload fields win when present, the cache
fills `discordNickname`, `discordId`, `avatarUrl`, `username` and org nicknames.

```tsx
// ✅
<UserAvatar user={player} />           // { user_id, username, avatar: <hash> }
<UserAvatar user={signup} />           // { user: 12, username }

// ❌ copying fields into a new object loses the cache lookup's inputs and drifts
<UserAvatar user={{ pk: p.pk, username: p.username, avatar: p.avatar }} />
```

Two exceptions:

- **The id is not the user's.** A row whose `id` belongs to something else (a
  subscription, an OrgUser) would resolve the wrong user. Drop it first:
  `const { id, ...subscriber } = row;` then pass `subscriber`.
- **The row says `user_pk`.** The resolver does not read `user_pk` yet, so map it:
  `<UserAvatar user={{ ...row, pk: row.user_pk }} />`.

A payload that names two people (e.g. a draft event's `captain_id` / `captain_name`
and `picked_id` / `picked_name`) is a translation, not a copy:
`DisplayName({ pk: payload.captain_id, username: payload.captain_name })`.

## The org comes from the page

The org whose server nicknames apply is derived from the current route and the
entity that page has loaded (`lib/displayOrg.ts`): org, league, tournament,
event, roll-call, hero-draft and Activity pages. Other pages have no org.

Don't pass an org:

```tsx
DisplayName(user)                      // ✅
DisplayName(user, undefined, orgId)    // ❌ draftforge/no-display-org-arg
```

The third argument is an override for the rare view that deliberately shows a
different org (or `null` for none); it needs a line-level disable with a reason.
Components that must react to the org (rather than render a name) use
`useDisplayOrgId()` from `~/lib/displayOrg`.

`DisplayName` is a plain function: text it produced updates on the component's
next render if a cache entry arrives later. `UserAvatar` subscribes and updates
on its own.

## Avatars

`<UserAvatar user={x} />` builds the Discord CDN URL from `avatarUrl`, or
`discordId` + avatar hash (cached `discordId` included), and falls back to the
name's initial.

- **No user** (a team without a captain, a TBD slot): pass `fallbackName` for the
  initials, e.g. `<UserAvatar user={team.captain} fallbackName={team.name} />`.
  Don't branch to a raw `<Avatar>`.
- **Sizes and borders:** `size="tiny|xs|sm|md|lg|xl"`, `border="captain"` (the
  yellow ring), `primary`, `muted`; extra classes via `className`.
- A raw `<AvatarImage src={x.avatar}>` gets a bare Discord hash and never loads.
- Non-person images (org and team logos) keep using `Avatar`/`AvatarImage`.

## Strings, toasts and attributes

Names in toasts, confirm dialogs, titles and `alt`/`aria-label`/`placeholder`
text are user-facing too: build them with `DisplayName(x)`.

Raw usernames are correct where nobody reads them as a name: logger calls,
`data-testid`, `key`, `id`, `className`, links and query keys. The lint rule
skips those.

## Deliberate single-field displays

Some UI shows one specific field on purpose: a labelled "Username:" row, an
`@handle` beside the display name, a meta image that
needs a URL string (`AvatarUrl(user)`). Keep the field and say why, on the line:

```tsx
{/* eslint-disable-next-line draftforge/use-display-name -- labelled username row */}
<span>{user.username}</span>
```

`frontend/eslint.config.js` registers the `draftforge` plugin with no rules on, so
these comments also resolve under `npm run lint`.

## Searching for people

A search box should find someone by any name they're shown or known by. Never
hand-roll `u.username.toLowerCase().includes(q)`: it misses Discord names, server
nicknames and names only the cache knows (`draftforge/use-user-search`).

| Need | Use |
| --- | --- |
| Filter users already loaded (a grid, a roster, a draft pool) | `useFilteredUsers(users, query, { excludePks })` from `~/hooks/useUserSearch`; plain `filterUsers` from `~/lib/userSearch` inside an existing `useMemo` |
| Test one user | `userMatchesQuery(user, query)` |
| Resolve typed text to one user (Enter on a free-text field) | `findUserByName(users, text)` |
| Search every site user on the server | `useUserSearch(query, { orgId, leagueId, enabled })` |
| Search an org's Discord server members | `useDiscordMemberSearch(query, orgId)` |
| Filter box above a grid | `<UserSearchInput value onChange placeholder />` |
| Pick a person from a list | `<UserPicker>` from `~/components/user/search` |

What matches: username, site nickname, Discord global name and the display name,
which includes the org server nickname on an org page (the org comes from the
page, as for `DisplayName`). Discord guild members match on `nick`,
`global_name` and `username`. The backend uses the same set (`user_name_q`, see
[backend.md](backend.md)) plus Discord username and Steam ID.

The server rejects queries under `USER_SEARCH_MIN_LENGTH` (3); the hooks debounce
by `USER_SEARCH_DEBOUNCE_MS` and stay idle below the minimum. Their `status` is
`too-short`, `searching`, `error` or `done`.

```tsx
const [query, setQuery] = useState('');
const search = useUserSearch(query, { orgId, enabled: open });
const candidates = search.results.filter((u) => u.membership === 'org');

<UserPicker
  query={query}
  onQueryChange={setQuery}
  results={candidates}            // or groups={[{ heading, users }]}
  status={search.status}          // omit for client-side lists
  onSelect={pick}
  isDisabled={(u) => onOtherTeam(u)}
  renderBadge={(u) => <Badge>{u.membership_label}</Badge>}
  testIds={{ input: 'x-search', option: (u) => `x-option-${u.pk}` }}
/>
```

`UserPicker` is a cmdk `Command` (keyboard navigation included) with no frame of
its own: put it in a `Popover` (`AddStandinPicker`), a `Dialog` (`WalkInPicker`) or
inline. Each row is `UserSearchOption`: avatar, display name, and the `@handle`
when it differs, so two people with the same name can be told apart. It renders at
most `limit` (50) rows and says how many more matched.

Results come back as the server's `SearchUserResult` (with `membership` and
`membership_label` when an org is passed). Query keys live in `userSearchKeys`;
`findSearchedUser` reads cached results by the `userSearch` prefix.

`AddUserModal` (site users and Discord members side by side, used to add members
to orgs, leagues, tournaments, events and admin teams) is built on the same hooks.
Use it for "add a member" flows rather than a new picker.

## Lint rules

All run in `npm run lint:shadcn` (pre-commit and CI); existing hits are
baselined in `frontend/shadcn-lint-suppressions.json`, so only new ones fail.

| Rule | Fix |
| --- | --- |
| <a id="use-display-name"></a>`draftforge/use-display-name` | Render the name with `DisplayName(x)`: JSX text, user-facing attributes, and strings (toasts, titles, team names). See [What a name resolves to](#what-a-name-resolves-to) and [Strings, toasts and attributes](#strings-toasts-and-attributes); a deliberate field gets a [reasoned disable](#deliberate-single-field-displays). |
| <a id="use-user-avatar"></a>`draftforge/use-user-avatar` | Replace the raw `<AvatarImage>` fed a user avatar with `<UserAvatar user={x} />`. See [Avatars](#avatars). |
| <a id="no-avatar-fallback"></a>`draftforge/no-avatar-fallback` | Use one `<UserAvatar user={x} fallbackName={…} />` instead of a raw `<Avatar>` branch or person initials in `<AvatarFallback>`. See [Avatars](#avatars). |
| <a id="no-display-org-arg"></a>`draftforge/no-display-org-arg` | Drop the org argument; it's derived from the page. See [The org comes from the page](#the-org-comes-from-the-page). |
| <a id="no-user-reshape"></a>`draftforge/no-user-reshape` | Pass the payload itself (`user={x}`), not a copy of its fields. See [Pass the payload as-is](#pass-the-payload-as-is). |
| <a id="use-user-search"></a>`draftforge/use-user-search` | Replace the hand-rolled `.toLowerCase().includes()` / `===` on a name field with `filterUsers`, `useFilteredUsers`, `userMatchesQuery` or `findUserByName`. See [Searching for people](#searching-for-people). |
| <a id="no-direct-name-resolver"></a>`draftforge/no-direct-name-resolver` | Use `DisplayName` / `<UserAvatar>` instead of `resolveDisplayName` / `AvatarUrl`. A URL string for a meta tag is a [deliberate exception](#deliberate-single-field-displays). |

## Testing

`UserAvatar` and `DisplayName` read the user cache and the route. In vitest:

- seed the cache with `useUserCacheStore.getState().upsert(user, { orgId })` and
  reset it in `beforeEach`;
- set the page with `window.history.pushState({}, '', '/organizations/2')` to get
  an org context (and back to `/` after);
- `UserPicker` is cmdk: `vitest.setup.ts` stubs the `ResizeObserver` and
  `scrollIntoView` it needs; options are `role="option"` and select on click;
- with no user and no image URL, `UserAvatar` renders only the initials (no
  `<img>`), so assert on the text.
