# People in the backend: name search

## Match names with `user_name_q`

`backend/org/user_search.py` builds the one `Q` for "find a user by name":

```python
from org.user_search import user_name_q

CustomUser.objects.filter(user_name_q(term, org_id=org.pk))
OrgUser.objects.filter(user_name_q(term, org_id=org.pk, prefix="user__"))
```

It matches, case-insensitively, `username`, the site nickname
(`base_profile__nickname`), `discordUsername`, `discordNickname` (the global
name) and, with `org_id`, that org's `OrgUser.guild_nickname`. `prefix`
searches through a relation. SQLite folds case for ASCII only.

Callers: `search_users` (`/api/users/search/`), promotion recipients
(`org/promotion/recipients.py`) and match suggestions
(`steam/services/match_suggestions.py`). A new name search uses it too. Don't
write `username__icontains` by hand: it drifts from what the frontend matches.

Exact lookups that identify one account (CSV import's `discordUsername__iexact`)
are not searches and stay as they are.

## `/api/users/search/`

`user/views_search.py: search_users`, behind `useUserSearch` on the frontend.

- `q`: at least 2 characters, or 400. A numeric `q` also matches `steamid` and
  `steam_account_id`.
- `org_id`: also matches that org's server nicknames, ranks its members first and
  annotates `membership` (`org`, `league`, `other_org`, null) and
  `membership_label`. Org staff only (403 otherwise), so the frontend sends it
  only for staff.
- `league_id`: with `org_id`, marks league members.
- Returns at most 20 `TournamentUserSerializer` rows.

## `/api/discord/search-discord-members/`

`discordbot/services/users.py: search_discord_members`, behind
`useDiscordMemberSearch`. Searches the org's Discord server members (cached in
Redis for an hour; `refresh-discord-members` refetches) on `nick`,
`global_name` and `username`, 2-character minimum, 20 results, each flagged
with `has_site_account` / `site_user_pk`.

## Keeping both sides in step

The frontend's `userSearchNames` (`frontend/app/lib/userSearch.ts`) and
`user_name_q` should cover the same names. The frontend user payload has no
`discordUsername` or Steam id, so those match only on the server. Adding a name
field means changing both, plus their tests (`app/lib/userSearch.test.ts` and
`backend/org/tests/test_user_search.py`).
