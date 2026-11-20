# Organization Settings

Organization settings hold org-wide policy: rules that apply to every event an
organization runs, as opposed to per-event or per-tournament options. They open in one
full-screen **settings modal** on the organization page, and the policy settings live in
one `OrgSettings` row per organization.
The API is listed in
[API Endpoints: Organization settings](../api/endpoints.md#organization-settings).

Every setting defaults to the platform's current behaviour, so an organization that
never opens the modal sees no change.

---

## The settings modal

An **Org Settings** button (cog icon) in the organization header opens the modal. The sidebar groups its sections
(a tab strip on phones, and a search box on both phones and desktop):

| Group | Sections |
|---|---|
| **Organization** | General, Discord, Members, Rules, Admin Team, Staff placement, Conduct (when the [conduct](organization-conduct.md) feature is unlocked) |
| **New Event Defaults** | Event, Tournament, Lobby, Discord, Ready check |

The **New Event Defaults** sections hold the values the create-event form pre-fills (see
[Events: Organization Event Defaults](events.md#organization-event-defaults)). They used
to open from a separate **Organization Event Defaults** dialog on the Events tab, which
is gone.

Editing any field shows one save bar at the bottom with **Discard** and **Save changes**. Save
changes writes every changed section, shows a "Settings saved" toast and leaves the modal open.
Closing the modal with unsaved edits asks "Discard unsaved changes?". A section with a
field error is marked in the sidebar and opens on save.

The open section is kept in the URL as `?settings=<section>`, so a link such as
`/organizations/12?settings=staff-placement` opens the modal on that section. Section
ids are `general`, `discord`, `members`, `rules`, `admins`, `staff-placement`, `conduct`,
`defaults-event`, `defaults-tournament`, `defaults-lobby`, `defaults-discord` and
`defaults-ready`. The older `?tab=settings&section=<id>` links are rewritten to
`?settings=<id>`.

---

## Who can see and edit settings

The Org Settings button and the modal are limited to org admins, the org owner and
site admins. Org staff and members do not see the button, so org staff can no longer edit
event defaults in the UI. A viewer without access who opens a `?settings=` link
has the parameter removed once their permissions load, and the modal does not open.

The org settings API (`/api/organizations/<id>/settings/`) enforces the same rule. The event
defaults API (`PATCH /api/events/defaults/<id>/`) still accepts org staff.

| Actor | View (GET) | Save (PATCH) |
|---|---|---|
| Anonymous | 401/403 | 401/403 |
| Org member or promoter | 403 | 403 |
| Org staff | 403 | 403 |
| Org admin | 200 | 200 |
| Org owner | 200 | 200 |
| Site admin (`is_staff` / `is_superuser`) | 200 | 200 |

Admins and owners of one organization get `403` on another organization's settings.
Denials use the coded body `{"code": "not_permitted", "detail": ...}`.

Site admins can also edit rows in Django admin under **Organization settings**. Admin
edits go through the same service as the API. Rows cannot be deleted there, and a row's
organization cannot be changed.

Every saved change writes an `OrgLog` entry (`action="update"`,
`details={"area": "settings", "changed_fields": [...]}`). Saving without changing
anything writes nothing.

---

## Staff placement

Staff can place a player on a roster even when the placement breaks a seating or
commitment rule. The **Staff placement** section sets what happens then.

!!! info "Applies as placement screens adopt it"
    The policy is read by the shared staff override check described in
    [Staff Overrides](../development/staff-overrides.md). Each screen that lets
    staff place members applies it once that screen uses the check.

| Policy | Meaning |
|---|---|
| **Silent** (default) | Staff placements ignore seating rules |
| **Confirm** | Staff must confirm a warning naming the broken rule |
| **Block** | Staff placements that break seating rules are refused |

**Seating rules staff are warned about** lists the rules the policy applies to. All of them are
ticked by default:

| Code | Rule |
|---|---|
| `gate_outside` | Outside the signup gate window |
| `gate_out_of_range` | Outside the gate's allowed range |
| `over_capacity` | Roster over capacity |
| `special_seat_role_mismatch` | Special seat given to the wrong role |
| `maybe_special_seat` | 'Maybe' member placed in a special seat |
| `maybe_forced_main` | 'Maybe' member forced into a main seat |

Eligibility and team rules (a missing Steam ID, MMR below the minimum, the stand-in cap
and so on) are not in this list. They always ask staff to confirm with a reason, whatever
the policy, and unticking a code never hides one.

---

## For developers

### Reading settings

Read settings with `get_org_settings` from `org.settings_service`. It accepts an
`Organization` or an existing organization id, and creates the row with defaults the
first time it is read. No migration backfills rows.

```python
from org.settings_constants import StaffOverridePolicy
from org.settings_service import get_org_settings

org_settings = get_org_settings(event.organization_id)
if org_settings.staff_override_policy == StaffOverridePolicy.CONFIRM:
    ...
```

!!! warning "Always use `get_org_settings`, never `org.settings`"
    `org.settings` raises `RelatedObjectDoesNotExist` for any organization whose row
    has not been created yet, which is most of them. `get_org_settings` is also the
    cached path.

!!! warning "Call it once per request, never per signup"
    Fetch the settings once per request or batch and pass the object down. Do not call
    `get_org_settings` inside a loop over signups. Inside `transaction.atomic`, cacheops
    may not serve the cached read, and a missing row runs `get_or_create`, a write
    inside the caller's transaction.

Write through `update_org_settings(org, actor=..., changes=...)`. It applies only
fields listed in `EDITABLE_FIELDS`, normalises warning codes, invalidates the cache after
commit, writes the `OrgLog` entry and logs `org_settings_updated`
(`system="org", subsystem="settings"`). Never update rows with `.update()` or a bare
`save()`: that skips the audit entry and can leave a stale cached row for up to an hour.

Treat any stored code that is not in `ALL_CODES` as absent. The API already filters
such codes out of its responses.

### Adding a setting

1. Add the field to `OrgSettings` in `backend/org/models_settings.py`, with a default
   that matches current behaviour, and run `just db::makemigrations org`.
2. Append the field name to `EDITABLE_FIELDS` in `backend/org/settings_service.py`.
3. Add it to `OrgSettingsSerializer.Meta.fields` in `backend/org/serializers.py`, with
   a field-level validator if the model does not already restrict the value.
4. Add it to `OrgSettingsSchema` in `frontend/app/components/api/orgSettingsAPI.ts`, and
   either extend an existing section's form or add a new section (below).
5. Add backend tests to `backend/org/tests/test_org_settings.py` (defaults, validation,
   permissions) and Vitest cases for the form, then document the setting on this page.

A `models.py` or migration change alters the test database hash, so CI runs one fresh
populate for that PR.

### Adding a settings section

The modal is a stack of independent sections. Each section has its own query and form,
reports its dirty state to the shared save bar (it has no Save button of its own), and
decides for itself who can see it. Register it in `ORG_SETTINGS_SECTIONS` in
`frontend/app/components/organization/tabs/orgSettings/sections.ts`:

```typescript
{
  id: 'notification-policy',
  label: 'Notifications',
  icon: Bell,
  group: 'Organization',
  useSection: useNotificationPolicySection,
  useVisible: useCanEditNotificationPolicy,
},
```

- `useSection(organizationId, enabled)` is a hook that returns `{ content, unit }`.
  `content` is the section body and `unit` is its save-bar unit (dirty state, save and
  discard). Pass `enabled` to the query so nothing is fetched for viewers who cannot
  open the section.
- `useVisible(org)` is a hook that returns whether the viewer can see the section. The
  list is static and every hook runs in list order on each render, so never add or
  remove entries at runtime.

The Org Settings button and the `?settings=` handling use `useOrgSettingsAccess`, which allows the modal
once access has settled and the viewer is an organization admin. The section must still gate its own edit controls,
and its endpoints must enforce the same permission.

A section can store its data somewhere other than `OrgSettings`, with its own model and
endpoint.

### Adding, removing or renaming a warning code

Codes are defined in `backend/org/settings_constants.py`. Each row stores its own list,
so existing rows never pick up a change to the defaults automatically.

To **add** a code:

1. Append it to `ALL_CODES` and add a label to `WARNING_CODE_LABELS` (the two key sets
   must match; a test checks this).
2. Update the literal list in `test_all_codes_pinned`.
3. Ship a data migration in the same PR that appends the code to every existing row's
   `staff_override_warning_codes`, unless the issue decides the code is opt-in.

To **remove or rename** a code, update `ALL_CODES`, the labels and the pinned test, and
ship a data migration that removes or renames the code in stored rows.

!!! danger "Data migrations hardcode the code strings"
    A migration that changes stored codes must spell out the literal strings
    (`"new_code"`). Never import `ALL_CODES` in a migration: the constant changes over
    time, and replaying history would apply the wrong list.

The frontend reads the code list and labels from `available_warning_codes` in the API
response, so a new code needs no frontend change. Each such migration changes the test
database hash, so CI runs one fresh populate for that PR.

### Where things live

| Part | File |
|---|---|
| Codes, labels, policy choices | `backend/org/settings_constants.py` |
| Model | `backend/org/models_settings.py` (re-exported from `org.models`) |
| Read and write services | `backend/org/settings_service.py` |
| API view | `backend/org/views_settings.py` |
| Serializer | `backend/org/serializers.py` (`OrgSettingsSerializer`) |
| Django admin | `backend/org/admin.py` (`OrgSettingsAdmin`) |
| API client and schemas | `frontend/app/components/api/orgSettingsAPI.ts` |
| Modal | `frontend/app/components/organization/OrgSettingsDialog.tsx` (shell: `components/patterns/SettingsDialog.tsx`) |
| Sections and access hook | `frontend/app/components/organization/tabs/orgSettings/` |
| New event defaults sections | `frontend/app/components/events/useOrgEventDefaultsSections.tsx` |
| Tests | `backend/org/tests/test_org_settings.py`, `frontend/app/components/organization/__tests__/OrgSettingsDialog.test.tsx`, `tabs/orgSettings/__tests__/`, `frontend/tests/playwright/e2e/19-org-features/06-org-settings.spec.ts` |
