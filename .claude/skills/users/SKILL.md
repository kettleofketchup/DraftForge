---
name: users
description: 'DraftForge people: rendering a person''s name (DisplayName) and avatar (UserAvatar), and searching for users (filterUsers, useUserSearch, UserPicker; backend user_name_q). Use when showing a person, building a user search box or picker, filtering users by name, or fixing a draftforge/use-display-name, use-user-avatar, use-user-search or other draftforge/* person lint error.'
---

# Users

A person is shown and found the same way everywhere: by the name the site
resolves for them (org server nickname, Discord global name, site nickname,
username), with the shared avatar.

| Task | Use | Reference |
| --- | --- | --- |
| Show a name | `DisplayName(user)` | [frontend.md](references/frontend.md#what-a-name-resolves-to) |
| Show an avatar | `<UserAvatar user={user} />` | [frontend.md](references/frontend.md#avatars) |
| Filter loaded users by name | `useFilteredUsers` / `filterUsers` | [frontend.md](references/frontend.md#searching-for-people) |
| Search all users on the server | `useUserSearch` | [frontend.md](references/frontend.md#searching-for-people) |
| Pick one person | `<UserPicker>` | [frontend.md](references/frontend.md#searching-for-people) |
| Add members to an org, league, tournament or event | `AddUserModal` | [frontend.md](references/frontend.md#searching-for-people) |
| Query users by name in Django | `user_name_q(term, org_id=…)` | [backend.md](references/backend.md) |

Rules:

- Pass the user payload as-is to `DisplayName` / `UserAvatar`; never pass an org
  or rebuild the name chain by hand.
- Never hand-roll a name match (`u.username.toLowerCase().includes(q)`); it misses
  Discord and server nicknames.
- Server searches need 3+ characters; the hooks handle the minimum and debounce.

The `draftforge/*` rules in `npm run lint:shadcn` enforce the frontend side (see
the `shadcn-lint` skill); every error links to its section in
[frontend.md](references/frontend.md#lint-rules).
