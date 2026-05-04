# Event League Combobox

**Status:** Implemented
**Date:** 2026-05-03
**Branch:** `feature/event-league-combobox`

## Summary

Replace the plain `<Select>` league field in `CreateEventModal` and `EditEventModal` with a searchable shadcn combobox on desktop and a shadcn `<Select>` on mobile. Extract a reusable `LeagueCombobox` component that lists the current organization's leagues, supports type-to-filter (desktop), and offers an explicit "Clear selection" option. Align the form schema between create and edit so league is optional in both (matching the nullable DB column).

## Motivation

- Organizations can accumulate many leagues; a long native `<Select>` is slow to scan.
- The current forms are inconsistent: Create treats league as optional, Edit enforces it as required via a Zod `.refine()`. The DB FK is nullable; the form should match.
- The codebase already has the building blocks: a working combobox pattern (`teamCombobox.tsx`), a `useLeagues(organizationId)` hook backed by Zustand, and shadcn `Command`/`Popover`/`Select` primitives.

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

`LeagueCombobox` is a domain-specific wrapper around shadcn primitives, mirroring the structure of `frontend/app/components/game/helpers/teamCombobox.tsx`. The file begins with `'use client'` to match the existing convention (no-op in this Vite SPA but consistent with the codebase).

The component branches on viewport via `useMediaQuery('(min-width: 768px)')`:

**Desktop (≥768px):**

```
LeagueCombobox (desktop)
├── Popover (open state controlled internally)
│   ├── PopoverTrigger → Button
│   │     variant="outline", role="combobox", aria-expanded={open},
│   │     aria-invalid={!!error}, w-full, justify-between
│   │     ├── <span className="truncate">{league name | placeholder}</span>
│   │     └── <ChevronsUpDown className="opacity-50" />
│   └── PopoverContent (className="w-[--radix-popover-trigger-width] p-0")
│       └── Command
│           ├── CommandInput (search, placeholder "Search leagues…")
│           └── CommandList
│               ├── CommandEmpty (loading | no leagues | no matches)
│               ├── CommandGroup (leagues)
│               │   └── CommandItem per league (Check icon when selected)
│               └── CommandGroup (actions, rendered only when value !== null)
│                   └── CommandItem "— Clear selection —"
```

**Mobile (<768px):** shadcn `<Select>` with `<SelectItem>` per league plus a leading `<SelectItem value="__clear__">— No league —</SelectItem>`. The component maps the sentinel back to `null` in the change handler. (No search on mobile — native-style picker is the better small-screen UX, and the mobile fallback in `teamCombobox.tsx` of "Mobile not supported" is a known gap we're not repeating.)

The component calls `useLeagues(organizationId)` internally so callers don't have to thread the data through.

## Component API

```tsx
type LeagueComboboxProps = {
  organizationId: number | undefined;
  value: number | null;          // selected league id, null when cleared
  onChange: (value: number | null) => void;
  disabled?: boolean;
  placeholder?: string;          // default: "Select league…"
  className?: string;            // forwarded to trigger Button / Select trigger
  id?: string;                   // for label association
  invalid?: boolean;             // sets aria-invalid on the trigger
};
```

Design notes:
- `value` is `number | null` (not `undefined`) so the cleared state is explicit and predictable in react-hook-form fields.
- `organizationId` is a prop rather than read from a global store internally — keeps the component testable and lets the caller decide refresh timing.
- The component does not expose loading/error props for content; it derives them from `useLeagues` and renders state in `CommandEmpty` (desktop) or as a disabled trigger with placeholder (mobile, where Select doesn't have an equivalent inline empty slot).
- `invalid` is a single boolean; the consumer (a `FormField` render prop) passes `!!fieldState.error`.

## UX States

**Desktop trigger button:**
| State | Display |
|---|---|
| Value selected | League name (truncated) + ChevronsUpDown |
| `value === null` | Placeholder ("Select league…") + ChevronsUpDown |
| `disabled` | Greyed out, popover won't open |
| `invalid` | `aria-invalid="true"` on Button (visual styling comes from shadcn Button defaults / the surrounding `FormItem`) |

**Desktop popover content:**
| State | Display |
|---|---|
| `organizationId === undefined` | Trigger disabled (defensive — should not occur in event modals) |
| `useLeagues.isLoading` | `<CommandEmpty>Loading leagues…</CommandEmpty>`; trigger remains enabled |
| Loaded, 0 leagues in org | `<CommandEmpty>No leagues in this organization</CommandEmpty>` |
| Loaded, search matches none | `<CommandEmpty>No leagues match "{query}"</CommandEmpty>` |
| Loaded, leagues present | `CommandGroup` of leagues (Check on selected) + a second `CommandGroup` containing "— Clear selection —" when a value is set |

**Mobile select:**
| State | Display |
|---|---|
| `organizationId === undefined` or 0 leagues | Disabled trigger with placeholder "No leagues" |
| `useLeagues.isLoading` | Disabled trigger with placeholder "Loading leagues…" |
| Loaded, leagues present | Items: "— No league —" first (maps to `null`), then one `<SelectItem>` per league |

**Clear semantics:**
- Desktop: a "Clear selection" `CommandItem` lives in its own `CommandGroup` at the bottom of the list, rendered only when `value !== null`. Selecting it closes the popover and calls `onChange(null)`.
- Mobile: the leading "— No league —" item carries a sentinel value (`"__clear__"`) that the component maps back to `null` before calling `onChange`. The item is always rendered, regardless of current value.
- Either way, no X icon on the trigger — all interactions stay inside the picker surface.

**Search (desktop only):**
- Client-side filter on league name (cmdk default). `useLeagues` returns the full org list, so no server round-trip per keystroke.

**Sizing:**
- Desktop trigger: `w-full` so it fills its `FormItem` cell.
- Desktop popover: `w-[--radix-popover-trigger-width]` so the dropdown matches trigger width.
- Mobile Select: full-width per shadcn defaults inside `FormItem`.

**Long names:**
- Trigger label uses `className="truncate"` (shadcn shorthand) so wide league names don't blow out the form layout.

## Schema & Form Changes

**`CreateEventModal.tsx`:**
- Replace the existing `<Select>` block (around lines 274-298) with `<LeagueCombobox organizationId={...} value={field.value ?? null} onChange={field.onChange} invalid={!!fieldState.error} />` inside the existing `<FormField>` / `<FormItem>` wrapper. `<FormMessage />` continues to render below.
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
1. **Search (desktop)**: open Create Event, open the combobox, type a partial league name, assert filtered list.
2. **Select**: pick a league, submit, assert event saved with the chosen league.
3. **Clear on create**: pick a league, then pick "Clear selection", submit, assert event saved with `tournament_league = null`.
4. **Clear on edit**: open an existing event that has a league, clear it, save, reload, assert league is empty.
5. **Mobile fallback**: with viewport set to <768px, verify the field renders as a `<Select>` with a "— No league —" first item that round-trips to `null`. (Use Playwright's viewport sizing — no separate spec file needed.)

**Backend:**
- No new tests required. During implementation, grep `tournament_league` in `backend/events/tests/` to confirm no existing test asserts that `null` is rejected.

**Frontend unit tests:**
- The project's frontend testing convention is Playwright-only (no Vitest setup referenced in CLAUDE.md). Skip component unit tests; rely on the E2E coverage above.

**Manual verification:**
- After implementing, run `just dev::debug`, open Create Event and Edit Event at desktop and mobile widths, exercise the five scenarios in a real browser before reporting the work complete.

## Risks & Open Questions

- **Default value shape in `EditEventModal`:** if it currently initializes `tournament_league` from a serializer that returns the league id under a different key (e.g., a nested object), the swap may surface a coercion bug. Mitigation: read the existing default-value setup during implementation and adjust before wiring the combobox.
- **Submit handler null handling:** if the modal currently strips falsy fields before PATCH (some forms do this to avoid sending `undefined`), `null` may be dropped and the league won't actually clear server-side. Mitigation: add a Playwright assertion that round-trips a cleared league through reload.
- **Mobile breakpoint inconsistency:** `teamCombobox.tsx` uses `768px` as the desktop cutoff. We match that here for consistency, but if the project later standardizes on a different breakpoint, both components should move together.

## Non-Goals

- Inline league creation
- TournamentFilterBar swap
- Any backend or migration changes
- Multi-select (events have a single league)
- Search on mobile (native-style Select is the better small-screen UX)
