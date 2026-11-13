# Tournament List

The `/tournaments` page is where players go to find a tournament to join or watch. It lists
tournaments from every organization on the site.

## Tabs

| Tab | Shows | Order |
|-----|-------|-------|
| **Upcoming** (default) | Tournaments that are `future` or `in_progress` and were played no more than 2 days ago (UTC) | Live first, then today and later, then the last two days |
| **Archived** | Everything else: finished tournaments and stale `future` ones | Newest first, 24 at a time with a **Load more** button |

The selected tab is kept in the URL (`?tab=archived`), so a link opens the same view.

## Your Organizations First

When a signed-in user belongs to at least one organization, the Upcoming tab splits into two
tiers:

1. **Your organizations**: tournaments from organizations you are a member of, admin or staff,
   or that own a league you admin or staff.
2. **Other organizations**: everything else.

Each tier keeps the Upcoming order above. If none of your organizations has an upcoming
tournament, the first tier says so and offers a **View archived** button.

The tiers are skipped (one flat list) for anonymous visitors, users without an organization,
and whenever an organization or league filter is set.

Membership comes from `member_organization_ids` on
[`/api/current_user`](../api/endpoints.md#current-user).

## Cards

Every card shows the tournament's organization: its logo, or a building icon when it has no
logo or the logo fails to load, next to the organization name ("No organization" when the
league has none). Tournaments that are in progress carry a **Live** badge.

## Search and Filters

- **Search** matches tournament, organization and league names (case-insensitive). It starts
  at 2 characters and waits briefly after typing stops.
- **Organization** and **League** dropdowns are kept in the URL
  (`?organization=1&league=2`), so a link can open the page pre-filtered.
- Filters apply to both tabs. An empty result offers a hint to clear them.

## API

The page reads [`GET /api/tournaments-list/`](../api/endpoints.md#tournament-list) with
`bucket=upcoming` (one unpaged request) or `bucket=archived&page=N` (paged).
