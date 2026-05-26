# Mobile Overflow Iteration Workflow

A repeatable loop for fixing mobile-viewport regressions (horizontal overflow,
hydration mismatch, cramped layouts). Built on three artifacts already on `main`:

- `frontend/tests/playwright/e2e/mobile/overflow-audit.spec.ts` — 11 routes × 3
  viewports × {overflow, hydration} audits.
- `frontend/scripts/find-overflow.ts` — DOM walker that returns offending
  elements with `domPath`, `overshootPx`, classes, computed width. Serializable
  through `page.evaluate()`.
- Playwright projects `mobile-pixel5` (393px), `mobile-iphone13` (390px),
  `mobile-iphone-se` (320px). Defined in `frontend/playwright.config.ts`.

## When to use

Reach for this loop whenever a diff has a chance of regressing mobile layout —
new components, navbar/header changes, dialog/modal work, anything that lays
out children horizontally, anything touching `@layer base` resets.

## The loop

Each pass is one orientation around the same axis. Run from repo root.

1. **Bring up the stack (once):** `just test::upd`. Use `just test::setup` if
   deps changed or this is a first run. Never raw `docker compose`.

2. **Pick the surface:** start with `mobile-iphone-se` (320px) — anything that
   survives 320px survives the other two. Drop down to a single route to
   iterate faster:
   ```bash
   just test::pw::spec mobile/overflow-audit --project=mobile-iphone-se \
     --grep "route 3"
   ```

3. **Read evidence, do not guess.** For every failure, read both:
   - `frontend/test-results/<test-name>/error-context.md` — the offender list
     serialized from `findOverflow()` (domPath, overshootPx, classes).
   - `frontend/test-results/<test-name>/test-failed-1.png` — the screenshot.

   Never debug from the test output alone. The error-context names the
   offending element; the screenshot tells you which surface it sits in.

4. **Translate to a fix via the right sibling skill:**
   | Symptom | Sibling skill | Why |
   |---|---|---|
   | Raw `<button>`, hand-rolled gradient, inline style | `brand` | Substitution tables for `<PrimaryButton>` / `<BrandDropdownMenu>` / `<BrandSelect>` / `<UserAvatar>` |
   | Layout primitive needed (flex/grid/scroll) | `ui-styling` + shadcn | Reach for `<ScrollArea>`, `<Collapsible>`, `flex-wrap` before custom CSS |
   | Hydration mismatch (not overflow) | `i18n-react` | `<html lang>` priority, prerendered-route flicker, cookie-vs-loader divergence |
   | Tailwind class fight (`h1` defeating utilities, `.container` missing) | `ui-styling` | Wrap element resets in `@layer base`; reintroduce `.container` rules explicitly |

5. **Prefer shared components, not local patches.** If two routes show the same
   offender, the fix belongs in `frontend/app/components/` (see how
   `<PageHeader>`, `<UserStrip nameMaxLength>`, `<BracketToolbar>` consolidated
   per-page overrides during PR #255).

6. **Re-run the same spec.** If it passes, expand to the full project:
   `just test::pw::spec mobile/overflow-audit --project=mobile-iphone-se`.
   When that's green, promote to `mobile-pixel5` and `mobile-iphone13`. Then
   run the full suite (all projects, no `--grep`) one time.

7. **Goal file is a checked-in artifact for the iteration, not memory.** Keep
   it under `docs/superpowers/specs/` only if it'll outlive the PR. Otherwise
   keep it gitignored (e.g. `/.local/`) and re-read it at the top of each
   iteration so context drift doesn't erase the spec.

## Parallelizing across skills via subagents

When the audit returns many independent failures, you can fan out:

- **`Explore`** to find every callsite of a brand component you're about to
  change (one quick search, single report).
- **`general-purpose`** for "rewrite component X to use `<BrandSelect>`,
  verify with `pnpm tsc`" — give it the exact file + the substitution from
  `/brand`. One agent per component, in parallel, all in one message.
- **`superpowers:code-reviewer`** after a batch of brand-related edits, to
  confirm the substitutions match the `/brand` review checklist.

Anti-pattern: do not dispatch two subagents that touch the same file in the
same message — they race. Group by file boundary.

## Common failure modes (and where they were solved during PR #255)

- **Tailwind v4 dropped `.container`** → reintroduce `.container` + clamp
  `[data-slot="scroll-area-viewport"] > div` to `display: block;` in
  `frontend/app/app.css`.
- **`<h1>` and `<Button>` defeat utilities** → wrap element resets in
  `@layer base` (see `6c775b0d`).
- **Hydration mismatch on prerendered routes** → `<html lang>` must be the
  authority client-side; cookie sync runs post-hydration. See
  `frontend/app/i18n/client.ts` and the `i18n-react` skill's `pitfalls.md`.
- **Nested grids squashed at 320px** (e.g. Match Details VS column) → use
  `grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]`, never a bare three-column
  fraction grid.
- **Inline lists wider than viewport** → `flex-wrap` + short mobile labels,
  not horizontal scroll containers.

## Verifying CI parity

The mobile audit is part of `@cicd`. To preview exactly what CI runs:
```bash
just test::pw::cicd-mobile
```
This runs the three mobile projects with the `@cicd` tag filter, matching
the `playwright.yml` matrix shard. If this is green locally, the CI shard
will be green.
