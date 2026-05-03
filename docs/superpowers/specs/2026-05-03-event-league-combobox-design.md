# Event League Combobox

**Status:** Draft
**Date:** 2026-05-03
**Branch:** `feature/event-reminder-pr3-docs`

## Summary

Replace the plain `<Select>` league field in `CreateEventModal` and `EditEventModal` with a searchable shadcn combobox. Extract a reusable `LeagueCombobox` component (Popover + cmdk Command) that lists the current organization's leagues, supports type-to-filter, and offers an explicit "Clear selection" option. Align the form schema between create and edit so league is optional in both (matching the nullable DB column).

## Motivation

- Organizations can accumulate many leagues; a long native `<Select>` is slow to scan.
- The current forms are inconsistent: Create treats league as optional, Edit enforces it as required via a Zod `.refine()`. The DB FK is nullable; the form should match.
- The codebase already has the building blocks: a working combobox pattern (`teamCombobox.tsx`), a `useLeagues(organizationId)` hook backed by Zustand, and shadcn `Command`/`Popover` primitives.

## Scope

In:
- New component: `frontend/app/components/league/LeagueCombobox.tsx`
- Edits to `CreateEventModal.tsx` and `EditEventModal.tsx` to consume it
- Drop the `.refine()` league-required check in `EditEventModal`

Out:
- `TournamentFilterBar` and other consumers of `useLeagues` (no proactive swaps)
- Inline league creation
- Any backend changes (`tournament_league` FK is already nullable)

## Architecture

`LeagueCombobox` is a domain-specific wrapper around shadcn primitives, mirroring the structure of `frontend/app/components/game/helpers/teamCombobox.tsx`:

```
LeagueCombobox
├── Popover (open state controlled internally)
│   ├── PopoverTrigger → Button (shows selected league name or placeholder)
│   └── PopoverContent
│       └── Command
│           ├── CommandInput (search)
│           ├── CommandEmpty (loading / no leagues / no matches)
│           ├── CommandList → CommandItem per league (Check icon if selected)
│           └── CommandItem "— Clear selection —" (rendered only when value !== null)
```

The component calls `useLeagues(organizationId)` internally so callers don't have to thread the data through.

## Component API

```tsx
type LeagueComboboxProps = {
  organizationId: number | undefined;
  value: number | null;          // selected league id, null when cleared
  onChange: (value: number | null) => void;
  disabled?: boolean;
  placeholder?: string;          // default: "Select league…"
  className?: string;            // forwarded to trigger Button
  id?: string;                   // for label association
};
```

Design notes:
- `value` is `number | null` (not `undefined`) so the cleared state is explicit and predictable in react-hook-form fields.
- `organizationId` is a prop rather than read from a global store internally — keeps the component testable and lets the caller decide refresh timing.
- The component does not expose loading/error props; it derives them from `useLeagues` and renders state in `CommandEmpty`.

## UX States

**Trigger button:**
| State | Display |
|---|---|
| Value selected | League name |
| `value === null` | Placeholder ("Select league…") |
| `disabled` | Greyed out, popover won't open |

**Popover content:**
| State | Display |
|---|---|
| `organizationId === undefined` | Trigger disabled with aria "Select an organization first" (defensive — should not occur in event modals) |
| `useLeagues.isLoading` | `<CommandEmpty>Loading leagues…</CommandEmpty>`; trigger remains enabled |
| Loaded, 0 leagues in org | `<CommandEmpty>No leagues in this organization</CommandEmpty>` |
| Loaded, search matches none | `<CommandEmpty>No leagues match "{query}"</CommandEmpty>` |
| Loaded, leagues present | List with Check on selected, pinned "— Clear selection —" item at bottom when a value is set |

**Clear semantics:**
- The "Clear selection" item is the only clear affordance (no X icon on trigger), keeping all interactions inside the Command surface.
- Hidden when `value === null` (no-op).
- Selecting it closes the popover and calls `onChange(null)`.

**Search:**
- Client-side filter on league name (cmdk default). `useLeagues` returns the full org list, so no server round-trip per keystroke.

## Schema & Form Changes

**`CreateEventModal.tsx`:**
- Replace the existing `<Select>` block (around lines 274-298) with `<LeagueCombobox organizationId={...} value={field.value ?? null} onChange={field.onChange} />` inside the existing `<FormField>` / `<FormItem>` wrapper.
- No Zod schema change — the field is already optional.

**`EditEventModal.tsx`:**
- Drop the Zod `.refine()` on `tournament_league` (around lines 57-58) so league is optional, matching the DB and `CreateEventModal`.
- Replace the `<Select>` with `<LeagueCombobox>` the same way.
- Verify the submit handler, dirty-tracking, and default-value initialization don't assume league is non-null. If they do, narrow the assumption — do not re-add the constraint.

**Form value normalization:**
- `field.value` may arrive as `number | undefined | null` depending on form defaults. The combobox always emits `number | null`. We coerce on read with `field.value ?? null` and trust `onChange` on write.
- The submit handler should serialize `null` to a `null` payload field; `EventSerializer` already accepts that since the FK is nullable.

## Testing

**Playwright E2E** (extend the existing event-modal spec, or add one):
1. **Search**: open Create Event, open the combobox, type a partial league name, assert filtered list.
2. **Select**: pick a league, submit, assert event saved with the chosen league.
3. **Clear on create**: pick a league, then pick "Clear selection", submit, assert event saved with `tournament_league = null`.
4. **Clear on edit**: open an existing event that has a league, clear it, save, reload, assert league is empty.

**Backend:**
- No new tests required. During implementation, grep `tournament_league` in `backend/events/tests/` to confirm no existing test asserts that `null` is rejected.

**Frontend unit tests:**
- The project's frontend testing convention appears to be Playwright-only (no Vitest setup referenced in CLAUDE.md). Skip component unit tests; rely on the E2E coverage above.

**Manual verification:**
- After implementing, run `just dev::debug`, open Create Event and Edit Event, exercise the four scenarios in a real browser before reporting the work complete.

## Risks & Open Questions

- **Default value shape in `EditEventModal`:** if it currently initializes `tournament_league` from a serializer that returns the league id under a different key (e.g., a nested object), the swap may surface a coercion bug. Mitigation: read the existing default-value setup during implementation and adjust before wiring the combobox.
- **Submit handler null handling:** if the modal currently strips falsy fields before PATCH (some forms do this to avoid sending `undefined`), `null` may be dropped and the league won't actually clear server-side. Mitigation: add a Playwright assertion that round-trips a cleared league through reload.

## Non-Goals

- Inline league creation
- TournamentFilterBar swap
- Any backend or migration changes
- Multi-select (events have a single league)
