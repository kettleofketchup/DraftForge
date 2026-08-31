# Auth Roles and Permission Matrix

This page is the **single source of truth** for the permission contract
across the eight roles in DraftForge. The matrix here mirrors what the
Playwright role-matrix tests enforce at runtime — if a row here drifts
from a row there, the tests fail (or you have a documentation bug).

> **Centralised contract.** When changing a UI gate, update:
>
> 1. The relevant hook in
>    [`frontend/app/hooks/usePermissions.ts`][hooks]
> 2. The matching backend helper in
>    [`backend/app/permissions_org.py`][permissions]
> 3. The expectations in the matrix spec under
>    [`frontend/tests/playwright/e2e/17-auth/`][matrix]
> 4. The corresponding row in this document
>
> Any one of those four out of sync produces silent permission drift.

## The Eight Roles

| Role          | Test fixture                      | Test user pk | Defining attribute                                                      |
| ------------- | --------------------------------- | -----------: | ----------------------------------------------------------------------- |
| `siteAdmin`   | `loginAdmin()`                    |         1001 | `is_superuser=True`                                                     |
| `siteStaff`   | `loginStaff()`                    |         1002 | `is_staff=True`, `is_superuser=False`                                   |
| `orgOwner`    | `loginAuthMatrixOrgOwner()`       |         1095 | `Organization.owner` FK (Auth Matrix Test Org, pk=8) — NOT in `admins`  |
| `orgAdmin`    | `loginAuthMatrixOrgAdmin()`       |         1090 | In `Organization.admins` (Auth Matrix Test Org, pk=8)                   |
| `orgStaff`    | `loginAuthMatrixOrgStaff()`       |         1091 | In `Organization.staff` (Auth Matrix Test Org, pk=8)                    |
| `orgMember`   | `loginAuthMatrixOrgMember()`      |         1092 | `OrgUser` row only, no admin/staff role                                 |
| `leagueAdmin` | `loginAuthMatrixLeagueAdmin()`    |         1093 | In `League.admins` (Auth Matrix League, pk=9)                           |
| `leagueStaff` | `loginAuthMatrixLeagueStaff()`    |         1094 | In `League.staff` (Auth Matrix League, pk=9)                            |
| `anonymous`   | _(none — fresh context)_          |            — | No session                                                              |

`orgOwner` is intentionally **not** in the `admins` M2M — only on the
`Organization.owner` FK. This lets the matrix verify the owner-implies-
admin cascade in `useIsOrganizationAdmin` / `has_org_admin_access`
independently of admin-set membership. The expectation is that
`orgOwner` matches `orgAdmin` everywhere except where the cascade can't
fire because of upstream store state (see the Edit User tournament row
below).

The non-site roles use **isolated** users + org + league (Auth Matrix
Test Org pk=8, Auth Matrix League pk=9) created by
`populate_auth_matrix_data`. Other suites must NOT touch these
entities — they exist purely to lock the role-context matrix. This
mirrors the feature-isolation rule in
`.claude/skills/testing/references/feature-isolation.md`.

The hierarchy is **site admin > org owner ≥ org admin > org staff >
league admin > league staff > org member > anonymous**. Each tier
inherits the abilities of the tiers below it (the bypass is implemented
in the `useIs*` hooks), **except** that staff roles do not cascade
upward into admin abilities — a league admin is _not_ an org admin and
an org staffer is _not_ an org admin.

Org owner and org admin are at the same logical tier — the permission
helpers treat them identically. They're distinct only at the data
model level: `Organization.owner` is a FK to one user, `Organization.admins`
is a M2M of zero-or-more users. The owner can't be removed; admins can.

## Site-Admin Cascade

`is_staff` and `is_superuser` are both treated as site-level admin. Both
the frontend hooks (`useIsOrganizationAdmin`, `useIsOrganizationStaff`,
`useIsLeagueAdmin`, `useIsLeagueStaff`) and the backend helpers
(`has_org_admin_access`, `has_league_admin_access`) short-circuit on
`is_staff || is_superuser` _before_ the entity-null guard. That means a
site admin can edit tournaments, declare winners on bracket nodes, and
generate brackets even when the tournament has no league or its org
hasn't loaded yet.

## Create-Action Matrix

The five entry points locked by `e2e/17-auth/01-create-gates.spec.ts`.
✓ = button visible to that role; ✗ = button hidden.

|                              | siteAdmin | siteStaff | orgOwner | orgAdmin | orgStaff | orgMember | leagueAdmin | leagueStaff | anonymous |
| ---------------------------- | :-------: | :-------: | :------: | :------: | :------: | :-------: | :---------: | :---------: | :-------: |
| Create Organization          |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✓     |      ✓      |      ✓      |     ✗     |
| Create League (org-detail)   |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✗      |      ✗      |     ✗     |
| Create Event (org-detail)    |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✗      |      ✗      |     ✗     |
| Create Event (`/events`)     |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✗      |      ✗      |     ✗     |
| Create Tournament            |     ✓     |     ✓     |    ✓     |    ✓     |    ✗     |     ✗     |      ✓      |      ✗      |     ✗     |

**Why some rows look this way:**

- **Create Organization** is the most permissive — any signed-in account
  can spin up its own org. The hook `useIsLoggedIn` plus
  `IsAuthenticated` on the backend `OrganizationView.create`.
- **Create League** and **Create Event** track `useIsOrganizationStaff` —
  events are operational, not governance, so staff get the gate. Both
  the org-detail tabs and `/events?organization=X` use the same hook.
- **Create Tournament** mirrors the backend's `has_league_admin_access`
  cascade via `useCanCreateAnyTournament`: site admin, admin of any
  organisation (via `admin_organization_ids`), or admin of any league
  (via `admin_league_ids`). Staff roles can't create tournaments —
  matching the backend's `perform_create` check.

## Edit + Bracket Matrix

The five entry points locked by `e2e/17-auth/02-edit-and-bracket-gates.spec.ts`.

|                                        | siteAdmin | siteStaff | orgOwner | orgAdmin | orgStaff | orgMember | leagueAdmin | leagueStaff | anonymous |
| -------------------------------------- | :-------: | :-------: | :------: | :------: | :------: | :-------: | :---------: | :---------: | :-------: |
| Edit User (org members tab)            |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✗      |      ✗      |     ✗     |
| Edit User (tournament players tab)     |     ✓     |     ✓     |    ✗     |    ✗     |    ✗     |     ✗     |      ✓      |      ✗      |     ✗     |
| Generate Bracket                       |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✓      |      ✓      |     ✗     |
| Set Bracket Match Winner               |     ✓     |     ✓     |    ✓     |    ✓     |    ✓     |     ✗     |      ✓      |      ✓      |     ✗     |
| Link Steam Match (bracket)             |     ✓     |     ✓     |    ✗     |    ✗     |    ✗     |     ✗     |      ✗      |      ✗      |     ✗     |

**Why some rows look this way:**

- **Edit User (org members tab)** uses `useIsOrganizationStaff(currentOrg)`
  via the UserCard's org-scoped editScope — staff-permissive.
- **Edit User (tournament players tab)** is a **known divergence**.
  The hasErrors panel renders first when a player profile is incomplete
  and uses the shared
  `resolveEditScope(user, { organizationId, leagueId, currentOrg, currentLeague })`,
  which returns `{ kind: 'league', league, orgId }` whenever the tournament
  has a league — it sets `orgId`, but still no `.organization` on the scope.
  `useScopedEditPermission` gates league scope on `scope.organization`, so
  this resolves to `useIsLeagueAdmin(league, undefined)`. The hook's org-admin cascade
  only fires if `league.organization` is embedded — in this navigation
  path it's not, so **org admins lose access**. Only site admins and
  direct league admins pass. Same user record, two gates depending on
  which page you're on, with an additional store-state dependency.

  The `orgId` the resolver carries makes the **PATCH target** deterministic
  (via `scopeToContext`), but it is not read by the permission gate, so it
  does not close this divergence.
- **Generate Bracket** and **Set Winner** use `useCanEditTournament` /
  `useIsLeagueStaff` — operational match-management actions that
  league staff legitimately do.
- **Link Steam Match** is another **known divergence**: gates on
  `useUserStore.isStaff()` (site staff/superuser only) while the rest
  of the MatchStatsModal uses `useIsLeagueStaff`. If you're widening
  it, lift the gate to `useIsLeagueStaff` and flip the matrix row.

## Adding a New Gate

1. Pick the right hook in `usePermissions.ts` — or add one if none fits
   (and document it in this page).
2. Apply the hook to the JSX gate. If the action also has a backend
   endpoint, make sure the backend's permission cascade lines up with
   the frontend hook's convention (site admin bypass, owner-counts-as-
   admin, etc.).
3. Add a `data-testid` to the gated button.
4. Append a row to whichever spec in `e2e/17-auth/` covers the action.
5. Update the matrix table in this page.

## Adding a New Role

The fixture file is `frontend/tests/playwright/fixtures/role-contexts.ts`.
A new role requires:

- A `TestUser` in `backend/tests/data/users.py` and the corresponding
  populate function in `backend/tests/populate/users.py`.
- A `/api/tests/login-<role>/` view in `backend/tests/test_auth.py` and
  URL entry in `backend/tests/urls.py`.
- A login fixture in `frontend/tests/playwright/fixtures/auth.ts`.
- An entry in `ROLE_NAMES` and `ROLE_LOGINS` in `role-contexts.ts`.
- An expectation column in **every** matrix table — both in this page
  and in `e2e/17-auth/*.spec.ts`.

If the new role scopes to an org or league, **wire it into the
auth-matrix org/league**, not DTX — keep the isolation intact. The
relevant populate file is `backend/tests/populate/auth_matrix.py`.

## Isolation Guarantees

The auth matrix owns:

| Resource                            |   pk | Created by                          |
| ----------------------------------- | ---: | ----------------------------------- |
| Auth Matrix Test Org                |    8 | `populate_auth_matrix_data`         |
| Auth Matrix League                  |    9 | `populate_auth_matrix_data`         |
| Auth Matrix No Bracket (tournament) |  200 | `populate_auth_matrix_data`         |
| Auth Matrix Pending Bracket         |  201 | `populate_auth_matrix_data`         |
| Auth Matrix Completed Bracket       |  202 | `populate_auth_matrix_data`         |
| `auth_matrix_org_owner` user        | 1095 | `populate_test_auth_users` + wiring |
| `auth_matrix_org_admin` user        | 1090 | `populate_test_auth_users` + wiring |
| `auth_matrix_org_staff` user        | 1091 | `populate_test_auth_users` + wiring |
| `auth_matrix_org_member` user       | 1092 | `populate_test_auth_users` + wiring |
| `auth_matrix_league_admin` user     | 1093 | `populate_test_auth_users` + wiring |
| `auth_matrix_league_staff` user     | 1094 | `populate_test_auth_users` + wiring |

Tournament pks land in the 200s (rather than 10–12) to sit clear of the
auto-incremented range used by other populate steps — the bracket
tournaments that DTX/Test Org create take pk 7+ via autoincrement, so
the explicit-pk creates in the auth-matrix step would collide if they
re-used the same range.

Other suites must not touch any of these. Conversely, the matrix
must not depend on DTX, league/org admins outside of this set, or
shared bracket tournaments — those are owned by their respective
feature suites.

## Related Files

| Concern                          | File                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------- |
| Frontend permission hooks         | `frontend/app/hooks/usePermissions.ts`                                                |
| Backend permission helpers        | `backend/app/permissions_org.py`                                                      |
| User serializer (role memberships)| `backend/app/serializers.py` (`UserSerializer`)                                       |
| Playwright role fixture           | `frontend/tests/playwright/fixtures/role-contexts.ts`                                 |
| Login endpoints                   | `backend/tests/test_auth.py`, `backend/tests/urls.py`                                 |
| Test users                        | `backend/tests/data/users.py`                                                         |
| Create-action matrix              | `frontend/tests/playwright/e2e/17-auth/01-create-gates.spec.ts`                        |
| Edit + bracket matrix             | `frontend/tests/playwright/e2e/17-auth/02-edit-and-bracket-gates.spec.ts`              |

[hooks]: ../../../frontend/app/hooks/usePermissions.ts
[permissions]: ../../../backend/app/permissions_org.py
[matrix]: ../../../frontend/tests/playwright/e2e/17-auth/
