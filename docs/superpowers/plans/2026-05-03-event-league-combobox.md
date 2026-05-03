# Event League Combobox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain `<Select>` league field in `CreateEventModal` and `EditEventModal` with a searchable shadcn `LeagueCombobox` (desktop) plus a `<Select>` fallback (mobile), and align the form schema so league is optional in both modals.

**Architecture:** A new domain wrapper component `LeagueCombobox` lives at `frontend/app/components/league/LeagueCombobox.tsx`. It internally calls `useLeagues(organizationId)`, branches on `useMediaQuery('(min-width: 768px)')`, and renders Popover+Command on desktop or Select on mobile. Both event modals consume it via react-hook-form's `<FormField>` render prop. Existing data-testids (`event-league-select`, `event-league-option-{pk}`, `edit-event-tournament-league`, `league-option-{pk}`) are preserved on the new trigger and item elements so existing Playwright specs keep working. Per the project's testing skill ("Always use `data-testid` selectors; never `getByPlaceholder`/`getByRole('option')` for interaction"), the component also exposes `searchTestId` and `clearTestId` props so the new search input and clear-sentinel items are addressable by test-id.

**Form composition:** This component is consumed via the project's existing react-hook-form `FormField` / `FormItem` / `FormControl` / `FormMessage` pattern (verified in `DiscordConfigSection.tsx`). We do **not** migrate to shadcn's newer `FieldGroup` / `Field` primitives — that would be a project-wide refactor outside this PR's scope.

**Tech Stack:** React 19, TypeScript, react-hook-form, Zod, shadcn/ui (Command, Popover, Select), cmdk, Tailwind, Playwright. Vite SPA (no Next.js).

**Spec:** `docs/superpowers/specs/2026-05-03-event-league-combobox-design.md`

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `frontend/app/components/league/LeagueCombobox.tsx` | Combobox/Select wrapper around `useLeagues`. Single file, ~180 lines including both viewport branches. |
| Modify | `frontend/app/components/events/CreateEventModal.tsx` | Replace the Select block at lines 272-298 with `<LeagueCombobox>`. |
| Modify | `frontend/app/components/events/EditEventModal.tsx` | Drop the Zod `.refine()` at lines 54-59; replace the Select block at lines 286-330 with `<LeagueCombobox>`; remove the now-unused local `useLeagues` call at line 79. |
| Modify | `frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts` | Add E2E tests for search, clear-on-create, mobile fallback. |
| Modify | `frontend/tests/playwright/e2e/16-events/10-edit-league-and-event-fields.spec.ts` | Add E2E test for clear-on-edit. |

---

## Pre-flight: Environment

Before starting tasks, ensure the test environment can run Playwright:

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/event-league-combobox
./dev                           # bootstrap venv + deps if not done already
cp ../../backend/.env ./backend/.env  # copy backend secrets
just db::migrate::all
just test::up                   # start test containers
just test::pw::install          # one-time: install Playwright browsers
```

Run the existing event spec once to confirm baseline is green:

```bash
just test::pw::spec 02-create-event
```

Expected: all tests pass against current `<Select>` implementation. If anything fails, do not proceed — fix the baseline first.

---

## Task 1: Survey existing event spec patterns

**Goal:** Before writing failing tests, read the existing spec file to understand its login/auth fixture, how it opens the Create Event modal, and how it submits. The new tests will mirror this style.

**Files:**
- Read: `frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts`
- Read: `frontend/tests/playwright/e2e/16-events/10-edit-league-and-event-fields.spec.ts`
- Read: `frontend/tests/playwright/fixtures/` (whatever auth/setup helpers live here)

- [ ] **Step 1: Read the create-event spec end-to-end**

```bash
cat frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts
```

Identify:
- The fixture used for login (e.g. `test` from `~fixtures/auth` or similar)
- How `eventInfo` (org id, league pk, alt league pk) is set up
- The pattern for opening the Create Event modal (route + button click)
- The pattern for submitting and asserting the API response

- [ ] **Step 2: Read the edit-league spec end-to-end**

```bash
cat frontend/tests/playwright/e2e/16-events/10-edit-league-and-event-fields.spec.ts
```

Identify the analogous patterns for edit flows.

- [ ] **Step 3: Note findings**

No code commit. Carry the patterns forward. In particular, note:
- The exact import path for fixtures (used in Tasks 2, 4, 8, 10)
- The `eventInfo` shape (used to know which league pks to select)
- Whether tests use API helpers to seed events or always go through the UI

---

## Task 2: Failing E2E — search + select via combobox in CreateEventModal

**Goal:** Add a Playwright test that types into a combobox search input and selects a league. It must fail today because the trigger is a plain `<Select>` (no `CommandInput` to type into).

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts`

- [ ] **Step 1: Add a new test case inside the existing `test.describe('Events - Create Event (@cicd)', ...)` block**

The existing `test.beforeAll` and `test.beforeEach` (lines 26-35) already provide `eventInfo` and log in as event admin. Add this test alongside the others (e.g. after `'creates a one-off event via modal'`):

```ts
test('league combobox: search filters and selects on create', async ({ page }) => {
  await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
  await page.getByTestId('org-tab-events').click();
  await page.getByTestId('create-event-btn').click();

  // Open the combobox trigger
  const trigger = page.getByTestId('event-league-select');
  await trigger.click();

  // Type into the cmdk search input — first 3 chars of the seeded league name
  await page.getByTestId('event-league-search').fill('Eve');

  // Pick the seeded events league via its preserved per-item data-testid
  await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();

  // Trigger should now show the selected league name
  await expect(trigger).toContainText('Events Test League');
});
```

- [ ] **Step 2: Run the test and verify it FAILS**

```bash
just test::pw::spec 02-create-event -g "search filters and selects"
```

Expected: FAIL. Most likely error: `getByTestId('event-league-search')` times out because the current `<SelectTrigger>` does not open a `CommandInput` and the `event-league-search` test-id doesn't exist yet. Note the failure mode in the test output — that's our red baseline.

- [ ] **Step 3: Commit the failing test**

```bash
git add frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts
git commit -m "test(events): failing E2E for league combobox search+select"
```

---

## Task 3: Implement LeagueCombobox (desktop) + wire into CreateEventModal

**Goal:** Make Task 2's test pass. Build the desktop branch of the combobox and replace the Select block in `CreateEventModal`.

**Files:**
- Create: `frontend/app/components/league/LeagueCombobox.tsx`
- Modify: `frontend/app/components/events/CreateEventModal.tsx` (lines 272-298)

- [ ] **Step 1: Create `LeagueCombobox.tsx` (desktop only for now)**

```tsx
'use client';

import { Check, ChevronsUpDown } from 'lucide-react';
import * as React from 'react';

import { Button } from '~/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '~/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { useLeagues } from '~/components/league/hooks/useLeagues';
import { cn } from '~/lib/utils';

export interface LeagueComboboxProps {
  organizationId: number | undefined;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  id?: string;
  invalid?: boolean;
  /** data-testid to apply to the trigger (preserves existing test-ids) */
  triggerTestId?: string;
  /** prefix for per-item data-testids: `${itemTestIdPrefix}${leagueId}` */
  itemTestIdPrefix?: string;
  /** data-testid for the search input (desktop only) */
  searchTestId?: string;
  /** data-testid for the Clear-selection item (desktop) and No-league sentinel (mobile) */
  clearTestId?: string;
}

export const LeagueCombobox: React.FC<LeagueComboboxProps> = ({
  organizationId,
  value,
  onChange,
  disabled,
  placeholder = 'Select league…',
  className,
  id,
  invalid,
  triggerTestId,
  itemTestIdPrefix,
  searchTestId,
  clearTestId,
}) => {
  const [open, setOpen] = React.useState(false);
  const { leagues, isLoading } = useLeagues(organizationId);

  const selected = value != null ? leagues.find((l) => l.pk === value) : null;
  const isOrgMissing = organizationId == null;
  const triggerDisabled = disabled || isOrgMissing;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-invalid={invalid || undefined}
          disabled={triggerDisabled}
          data-testid={triggerTestId}
          className={cn(
            'w-full justify-between aria-invalid:border-destructive',
            className,
          )}
        >
          <span className="truncate">
            {selected ? selected.name : placeholder}
          </span>
          <ChevronsUpDown data-icon="inline-end" className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0">
        <Command>
          <CommandInput
            placeholder="Search leagues…"
            className="h-9"
            data-testid={searchTestId}
          />
          <CommandList>
            <CommandEmpty>
              {isLoading
                ? 'Loading leagues…'
                : leagues.length === 0
                  ? 'No leagues in this organization'
                  : 'No leagues match your search'}
            </CommandEmpty>
            {leagues.length > 0 && (
              <CommandGroup>
                {leagues.map((league) => (
                  <CommandItem
                    key={league.pk}
                    value={league.name}
                    data-testid={
                      itemTestIdPrefix ? `${itemTestIdPrefix}${league.pk}` : undefined
                    }
                    onSelect={() => {
                      onChange(league.pk);
                      setOpen(false);
                    }}
                  >
                    {league.name}
                    <Check
                      className={cn(
                        'ml-auto',
                        value === league.pk ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {value !== null && (
              <CommandGroup>
                <CommandItem
                  value="__clear__"
                  data-testid={clearTestId}
                  onSelect={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                >
                  — Clear selection —
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};

export default LeagueCombobox;
```

- [ ] **Step 2: Replace the Select block in `CreateEventModal.tsx`**

Edit `frontend/app/components/events/CreateEventModal.tsx`:

Add this import alongside the existing imports near the top of the file (after the other `~/components/league` import or with other component imports):

```tsx
import { LeagueCombobox } from '~/components/league/LeagueCombobox';
```

Then replace lines 272-298 (the entire `<FormField name="tournament_league" ...>` block including its `<Select>` children) with:

```tsx
<FormField
  control={form.control}
  name="tournament_league"
  render={({ field, fieldState }) => (
    <FormItem>
      <FormLabel>League</FormLabel>
      <FormControl>
        <LeagueCombobox
          organizationId={organizationId}
          value={field.value ?? null}
          onChange={(v) => field.onChange(v ?? undefined)}
          invalid={!!fieldState.error}
          triggerTestId="event-league-select"
          itemTestIdPrefix="event-league-option-"
          searchTestId="event-league-search"
          clearTestId="event-league-clear"
        />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

Note: `field.onChange(v ?? undefined)` — the form's existing default uses `undefined` for unset (line 93: `tournament_league: orgDefaults.tournament_league ?? undefined`), so we map combobox's `null` back to `undefined` to avoid changing the form-level shape.

- [ ] **Step 3: Run the failing test from Task 2**

```bash
just test::pw::spec 02-create-event -g "search filters and selects"
```

Expected: PASS. The combobox opens, search filters, item click selects, and trigger shows the league name.

- [ ] **Step 4: Run the rest of the file to confirm no regressions**

```bash
just test::pw::spec 02-create-event
```

Expected: all tests in the file pass. The existing tests at lines 116, 142, 201 click `event-league-select` then `event-league-option-{pk}` — both data-testids are preserved on the new combobox, so those tests should still pass.

If any existing test fails, debug before proceeding. Most likely cause: an existing test relied on Select-specific keyboard behavior (e.g. typing a letter to jump to an option). Such tests need to be updated to use the new combobox search input.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/league/LeagueCombobox.tsx \
        frontend/app/components/events/CreateEventModal.tsx
git commit -m "feat(league): add LeagueCombobox + wire into CreateEventModal"
```

---

## Task 4: Failing E2E — clear on create

**Goal:** Add a test that picks a league, then clears via the in-list "— Clear selection —" item, and asserts the submitted event has `tournament_league: null`. It must fail today because the combobox doesn't render the Clear item yet — wait, actually Task 3's component already includes the Clear item. Verify by inspecting the file and adjust this task accordingly.

Re-reading Task 3's code: yes, the Clear item is already implemented. This task therefore tests that the wiring works end-to-end through the API. It will likely pass on first run, but we still write the test first to document the contract.

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts`

- [ ] **Step 1: Add the test case**

Append to the same `test.describe` block. The fill-and-submit pattern below mirrors `'creates a one-off event via modal'` at lines 105-130 of the existing spec file.

```ts
test('league combobox: clear selection on create submits null', async ({ page }) => {
  await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
  await page.getByTestId('org-tab-events').click();
  await page.getByTestId('create-event-btn').click();

  // Pick a league
  await page.getByTestId('event-league-select').click();
  await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();

  // Reopen and clear
  await page.getByTestId('event-league-select').click();
  await page.getByTestId('event-league-clear').click();

  // Trigger should show the placeholder again
  await expect(page.getByTestId('event-league-select')).toContainText(/select league/i);

  // Fill the rest of the required fields (mirroring the one-off-event test)
  await page.getByTestId('event-name-input').fill('E2E Clear-League Test');
  await page.getByTestId('event-tournament-name-input').fill('E2E Tournament');
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  await page.getByTestId('event-scheduled-input').fill(tomorrow.toISOString().slice(0, 16));

  // Capture the POST payload as the form submits
  const createReqPromise = page.waitForRequest(
    (req) => req.url().includes('/api/events') && req.method() === 'POST',
  );
  await page.getByTestId('form-dialog-submit').click();
  const createReq = await createReqPromise;

  const body = createReq.postDataJSON();
  expect(body.tournament_league ?? null).toBeNull();
});
```

- [ ] **Step 2: Run the test and observe**

```bash
just test::pw::spec 02-create-event -g "clear selection on create"
```

Two outcomes are possible:

**(a) PASS:** the combobox + form wiring already round-trips null correctly. Skip Step 3, jump to Step 4.

**(b) FAIL:** the form's submit pipeline is dropping null (the spec's "Risks & Open Questions" called this out). Proceed to Step 3.

- [ ] **Step 3 (only if Step 2 failed): Fix null-handling in CreateEventModal submit**

Open `CreateEventModal.tsx` and locate the submit handler (search for `createEvent(` — likely the function passed to `form.handleSubmit`). If the payload is built by spreading form values, ensure `tournament_league` is explicitly included even when `undefined`/`null`:

```tsx
const payload = {
  ...values,
  tournament_league: values.tournament_league ?? null,
};
await createEvent(payload);
```

Re-run Step 2; expect PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts \
        frontend/app/components/events/CreateEventModal.tsx
git commit -m "test(events): clear selection round-trips null on create"
```

(If Step 3 wasn't needed, the second `git add` path is omitted.)

---

## Task 5: Update EditEventModal — drop `.refine()` + swap Select

**Goal:** Make the edit modal consistent with create. Drop the league-required Zod refinement, replace the Select with `LeagueCombobox`, and remove the now-unused local `useLeagues` call.

**Files:**
- Modify: `frontend/app/components/events/EditEventModal.tsx`

- [ ] **Step 1: Drop the `.refine()` on `tournament_league`**

In `EditEventModal.tsx`, replace lines 50-59 (the comment block and the refined nullable schema) with:

```ts
  tournament_league: z.number().nullable(),
```

The schema property now reads as a simple nullable number — no UI-level required check, matching the DB column.

- [ ] **Step 2: Add the LeagueCombobox import**

Add near the existing imports:

```tsx
import { LeagueCombobox } from '~/components/league/LeagueCombobox';
```

- [ ] **Step 3: Remove the now-unused `useLeagues` call**

Line 79 currently reads:

```tsx
const { leagues, isLoading: isLoadingLeagues } = useLeagues(event?.organization);
```

`leagues` and `isLoadingLeagues` are used only inside the league `<Select>` block at lines 286-330. After the swap, neither is referenced. Delete this line. Also remove the now-unused import `import { useLeagues } from '~/components/league/hooks/useLeagues';` (line 27).

- [ ] **Step 4: Replace the league `<Select>` block**

Replace the entire `<FormField name="tournament_league" ...>` block (starting at line 286, ending at the closing `}` of the `render` prop and the closing `/>` of the FormField — verify by reading the current file):

```tsx
<FormField
  control={form.control}
  name="tournament_league"
  render={({ field, fieldState }) => (
    <FormItem>
      <FormLabel>League</FormLabel>
      <FormControl>
        <LeagueCombobox
          organizationId={event?.organization}
          value={field.value ?? null}
          onChange={(v) => field.onChange(v)}
          invalid={!!fieldState.error}
          triggerTestId="edit-event-tournament-league"
          itemTestIdPrefix="league-option-"
          searchTestId="edit-event-league-search"
          clearTestId="edit-event-league-clear"
        />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

Note: unlike Create, here we pass `v` straight through to `field.onChange` because the form value type is `number | null` (the schema is `z.number().nullable()`).

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. If there are errors about unused imports or unreachable code from the removed `noLeagues` variable, clean them up.

- [ ] **Step 6: Run the existing edit spec to confirm no regressions**

```bash
just test::pw::spec 10-edit-league-and-event-fields
```

Expected: existing tests pass — including `'edit event tournament_league happy path'` at line 123, which clicks `edit-event-tournament-league` then `league-option-${pk}`. Both test-ids are preserved.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/events/EditEventModal.tsx
git commit -m "feat(events): swap edit-modal league Select for LeagueCombobox + drop required refine"
```

---

## Task 6: Failing E2E — clear on edit

**Goal:** Add a test that opens an event with a league, clears it via the combobox, saves, reloads, and asserts the league is empty.

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/10-edit-league-and-event-fields.spec.ts`

- [ ] **Step 1: Add the test case**

Append to the `test.describe.serial('Edit league + event fields @cicd', ...)` block. The setup mirrors the existing `'edit event tournament_league happy path'` test (lines 123-156). Note: this file uses `loginAdmin` (site superuser), and the event detail page uses `event-edit-btn` test-id.

```ts
test('edit event tournament_league: clear via combobox', async ({ page, context }) => {
  const eventInfo = await getEventsTestData(context);
  await loginAdmin(context);

  await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
  await expect(page.getByTestId('event-edit-btn')).toBeVisible({ timeout: 15000 });
  await page.getByTestId('event-edit-btn').click();

  // Open combobox and pick Clear
  await page.getByTestId('edit-event-tournament-league').click();
  await page.getByTestId('edit-event-league-clear').click();

  // Trigger shows the placeholder
  await expect(page.getByTestId('edit-event-tournament-league')).toContainText(/select/i);

  // Save (the modal uses form-dialog-submit, scoped to the edit-event-modal)
  await page.getByTestId('edit-event-modal').getByTestId('form-dialog-submit').click();

  // Wait for the modal to close — confirms the PATCH completed
  await expect(page.getByTestId('edit-event-modal')).not.toBeVisible({ timeout: 10000 });

  // API sanity-check
  const apiResp = await context.request.get(`/api/events/${eventInfo.pk}/`);
  expect(apiResp.status()).toBe(200);
  const body = await apiResp.json();
  expect(body.tournament_league).toBeNull();

  // Revert so subsequent tests in the suite see the canonical league
  await patchWithCsrf(context, `/api/events/${eventInfo.pk}/`, {
    tournament_league: eventInfo.eventsLeaguePk,
  });
});
```

- [ ] **Step 2: Run and observe**

```bash
just test::pw::spec 10-edit-league-and-event-fields -g "clear via combobox"
```

Outcomes:

**(a) PASS:** edit modal's PATCH already round-trips null. Jump to Step 4.

**(b) FAIL:** PATCH payload is stripping null. Proceed to Step 3.

- [ ] **Step 3 (only if Step 2 failed): Fix null-handling in EditEventModal submit**

Search `EditEventModal.tsx` for the submit handler (look for `mutation.mutate` or `mutation.mutateAsync`). If the payload is built by spreading form values, explicitly ensure `tournament_league` is sent as `null` rather than dropped:

```tsx
mutation.mutate({
  ...values,
  tournament_league: values.tournament_league ?? null,
});
```

Re-run Step 2; expect PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/16-events/10-edit-league-and-event-fields.spec.ts \
        frontend/app/components/events/EditEventModal.tsx
git commit -m "test(events): clear via combobox round-trips null on edit"
```

(Drop the second path if Step 3 wasn't needed.)

---

## Task 7: Failing E2E — mobile fallback

**Goal:** Add a Playwright test that sets a mobile viewport and asserts the league field renders as a `<Select>`, including a "— No league —" first item that round-trips to `null`. It must fail today because `LeagueCombobox` only has the desktop branch.

**Files:**
- Modify: `frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts`

- [ ] **Step 1: Add the mobile test case**

Add to the same `test.describe('Events - Create Event (@cicd)', ...)` block as Tasks 2 and 4.

```ts
test('league combobox: mobile renders a Select fallback with clear sentinel', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 }); // iPhone 13-ish

  await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
  await page.getByTestId('org-tab-events').click();
  await page.getByTestId('create-event-btn').click();

  const trigger = page.getByTestId('event-league-select');

  // Mobile branch uses shadcn Select — there should be no cmdk search input.
  await trigger.click();
  await expect(page.getByTestId('event-league-search')).toHaveCount(0);

  // The "— No league —" sentinel should round-trip to null in the form.
  await page.getByTestId('event-league-clear').click();
  await expect(trigger).toContainText(/select league/i);

  // Picking a real league still works
  await trigger.click();
  await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();
  await expect(trigger).toContainText('Events Test League');
});
```

- [ ] **Step 2: Run and verify FAIL**

```bash
just test::pw::spec 02-create-event -g "mobile renders a Select fallback"
```

Expected: FAIL. The assertion `toHaveCount(0)` on `event-league-search` will fail because the desktop branch (with the `CommandInput`) renders even at small viewport widths until the mobile branch is added. Or the test fails on the next step because `event-league-clear` doesn't exist as a Select item. Either failure mode is the red baseline.

- [ ] **Step 3: Commit the failing test**

```bash
git add frontend/tests/playwright/e2e/16-events/02-create-event.spec.ts
git commit -m "test(events): failing E2E for mobile Select fallback"
```

---

## Task 8: Implement mobile fallback in LeagueCombobox

**Goal:** Make Task 7 pass. Add the mobile branch that renders a shadcn `<Select>` with a leading sentinel item.

**Files:**
- Modify: `frontend/app/components/league/LeagueCombobox.tsx`

Note: `@uidotdev/usehooks` is already used in the codebase (see `teamCombobox.tsx:3`). No new dependency needed.

- [ ] **Step 1: Add the mobile branch**

At the top of `LeagueCombobox.tsx`, add imports:

```tsx
import { useMediaQuery } from '@uidotdev/usehooks';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
```

Inside the component body, after `const { leagues, isLoading } = useLeagues(...)`, add:

```tsx
const isDesktop = useMediaQuery('(min-width: 768px)');
```

Then, before the existing `return (<Popover>...)`, insert the mobile branch:

```tsx
if (!isDesktop) {
  const noLeagues = !isLoading && leagues.length === 0;
  return (
    <Select
      value={value != null ? String(value) : ''}
      onValueChange={(v) => {
        if (v === '__clear__') {
          onChange(null);
        } else {
          onChange(parseInt(v, 10));
        }
      }}
      disabled={triggerDisabled || noLeagues}
    >
      <SelectTrigger
        id={id}
        data-testid={triggerTestId}
        aria-invalid={invalid || undefined}
        className={cn('w-full', className)}
      >
        <SelectValue
          placeholder={
            isLoading
              ? 'Loading leagues…'
              : noLeagues
                ? 'No leagues in this organization'
                : placeholder
          }
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__clear__" data-testid={clearTestId}>
          — No league —
        </SelectItem>
        {leagues.map((league) => (
          <SelectItem
            key={league.pk}
            value={String(league.pk)}
            data-testid={
              itemTestIdPrefix ? `${itemTestIdPrefix}${league.pk}` : undefined
            }
          >
            {league.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

The existing desktop `return (<Popover>...)` stays as the fall-through for `isDesktop === true`.

- [ ] **Step 2: Run the mobile test**

```bash
just test::pw::spec 02-create-event -g "mobile renders a Select fallback"
```

Expected: PASS.

- [ ] **Step 3: Run the full event create spec to confirm no regressions**

```bash
just test::pw::spec 02-create-event
```

Expected: all tests pass (desktop tests still pick up the desktop branch since the default Playwright viewport is 1280×720).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/league/LeagueCombobox.tsx
git commit -m "feat(league): add mobile Select fallback to LeagueCombobox"
```

---

## Task 9: Manual browser verification

**Goal:** Per the project's CLAUDE.md ("UI changes need browser verification"), exercise the feature in a real browser at both desktop and mobile widths before declaring done.

**Files:** none (verification only)

- [ ] **Step 1: Start the dev environment**

```bash
just dev::debug
```

Wait for the frontend to compile and the page to be reachable at the dev URL.

- [ ] **Step 2: Desktop verification (default browser width)**

In a real browser, with a logged-in user that has at least one organization with multiple leagues:

1. Navigate to an organization's events page.
2. Click "Create Event" — verify the League field shows a button with placeholder "Select league…" and a chevron.
3. Click it — popover opens with search input and league list.
4. Type a partial league name — list filters in real time.
5. Click a league — popover closes, button shows the league name (truncated if long).
6. Click the button again — popover reopens, shows Check next to the selected league, plus "— Clear selection —" at the bottom.
7. Click "Clear selection" — popover closes, button shows the placeholder again.
8. Pick a league, fill required fields, submit — event creates successfully.
9. Open the new event in Edit mode — verify the league shows correctly.
10. In Edit mode, clear the league via the combobox, save — page reloads, edit again, league is empty. ✅

- [ ] **Step 3: Mobile verification (DevTools device emulation, viewport <768px)**

1. Open DevTools, set viewport to e.g. iPhone SE (375×667).
2. Repeat the Create flow from Step 2: the field should now render as a native-style Select trigger (no chevron+search popover; an OS-style dropdown).
3. Verify the dropdown shows "— No league —" at the top, then leagues.
4. Pick "— No league —" — trigger shows placeholder again.
5. Pick a league, submit — event creates successfully.

- [ ] **Step 4: Stop the dev environment**

```bash
just dev::down
```

- [ ] **Step 5: No commit needed** (verification only, no file changes)

---

## Task 10: Final spec/plan status update + cleanup commit

**Goal:** Reflect that the work is complete and ready for review.

**Files:**
- Modify: `docs/superpowers/specs/2026-05-03-event-league-combobox-design.md` (status only)

- [ ] **Step 1: Bump spec status**

In the spec file header, change `**Status:** Approved` to `**Status:** Implemented`.

- [ ] **Step 2: Confirm full Playwright event suite is green**

```bash
just test::pw::spec 16-events
```

Expected: all tests pass (the entire `16-events` directory).

- [ ] **Step 3: Confirm no stray uncommitted changes**

```bash
git status
```

Expected: clean working tree (modulo the spec status bump from Step 1, which we'll commit next).

- [ ] **Step 4: Commit the status bump**

```bash
git add docs/superpowers/specs/2026-05-03-event-league-combobox-design.md
git commit -m "docs(spec): mark league combobox spec implemented"
```

- [ ] **Step 5: Show the branch's commit log**

```bash
git log --oneline main..HEAD
```

This is the change set ready for PR / merge.

---

## Definition of Done

- `LeagueCombobox` exists at `frontend/app/components/league/LeagueCombobox.tsx` and renders desktop Popover+Command and mobile Select branches.
- `CreateEventModal` and `EditEventModal` both use `LeagueCombobox` for the `tournament_league` field.
- The Zod `.refine()` on `tournament_league` in `EditEventModal` is gone; both modals treat the field as optional.
- All Playwright tests in `frontend/tests/playwright/e2e/16-events/` pass, including five new cases:
  1. Search + select on create
  2. Clear-on-create round-trips `null`
  3. Clear-on-edit round-trips `null`
  4. Mobile renders Select fallback
  5. (No standalone test for "select happy path" — covered by existing tests via preserved data-testids)
- Manual desktop + mobile browser checks pass.
- Spec status is `Implemented`.
