# Layout overlap sweep

The `layout` Playwright project fails when content overlaps other content or paints
outside the container that should clip it. jsdom has no layout engine, so unit tests
cannot see either.

## Files

| File | Role |
|------|------|
| `frontend/tests/playwright/fixtures/layoutProbe.ts` | In-page detector, serialised by `page.evaluate()`; closes over nothing |
| `frontend/tests/playwright/fixtures/layout.ts` | `prepareLayoutProbe`, `sweepLayout`, report formatting, quarantine loading and matching |
| `frontend/tests/playwright/e2e/layout/routes.spec.ts` | Every audit route at 375x667 then 1440x900, with the scroll walk on |
| `frontend/tests/playwright/e2e/layout/detector-selftest.spec.ts` | Injected fixtures proving each rule fires and stays quiet; `retries: 0` |
| `frontend/tests/playwright/layout-known-findings.json` | Quarantine of known findings |
| `frontend/tests/playwright/helpers/audit-routes.ts` | Route list shared with the mobile overflow audit |

## Running

```bash
just test::pw::cicd-layout                                    # what CI runs
just test::pw::run --project=layout --no-deps tests/playwright/e2e/layout/routes.spec.ts
```

The project starts at 375x667 and is not `isMobile`, because the sweep widens the
same document to 1440x900.

## What it reports

- **collision**: two in-flow leaf/text elements in the same positioning frame overlap by
  at least 64px². Fixed and sticky subtrees, dialogs, popovers, selects and tooltips are
  excluded; they layer by design.
- **escape**: part of an element (at least 2px thick and 256px²) lies outside its clip
  ancestor, and `elementFromPoint` in that strip lands on the element, its subtree, or
  a `pointer-events:none` ancestor that paints it. Geometry alone is never reported.

Each finding names a **state**: `base`, or `scroll:<container>@<fraction>`. A container
is named by its own `data-testid`/`id`, else by its nearest named ancestor plus its
`data-slot` (`~2`, `~3` break ties). Page content lives in the `#outlet_root` scroll
area, state `scroll:outlet_root>scroll-area-viewport@<fraction>`, so findings below the
first screen show up only there.

A finding must survive a 300ms re-measure. While a state is measured, timers of 250ms or
more are held and started afterwards, so polling cannot move boxes mid-measure and no
retry or debounced handler is lost.

The route test also fails when a state was skipped over the time budget or was still
loading (an on-screen skeleton, `aria-busy`, or image) when measured: an unmeasured state
must not pass as a clean one. `unprobeable` is reported, not gated. Route tests do not
retry.

## A red route

1. Read the failure message: viewport, state, both labels, and the escaped rect.
2. The `layout-states` and `layout-ledger` attachments show every state attempted,
   whether it settled, and the blind-spot counters (`unprobeable`, `unsettled`,
   `skipped`).
3. Fix the layout. If the fix belongs to another PR, quarantine it instead.

## Quarantine

Add a row to `layout-known-findings.json`:

```json
{
  "route": "/events/:eventId",
  "viewport": "1440x900",
  "state": "scroll:outlet_root>scroll-area-viewport@1",
  "kind": "escape",
  "findingKey": "<elKey, or 'keyA keyB' for a collision>",
  "owner": "<github login>",
  "issue": "#123",
  "note": "why it is not fixed here",
  "added": "YYYY-MM-DD"
}
```

`route` is the route's `name` in `helpers/audit-routes.ts`, never a resolved path, so
rows survive a reseed. Matching is exact on route, viewport, state, kind and key. The key
is text-free, `tag|testid|firstClass|@anchor/sibling.path`, with the path starting at
the nearest ancestor that has a `data-testid` or hand-written `id`. A quarantined finding that stops firing fails the
route as stale until its row is deleted. `"intermittent": true` is the only exemption.

## Changing the detector

Every rule has a self-test with a true positive, a correctly-clipped negative, a shape
guard and a membership guard. Break the rule you change and confirm its self-test goes
red before trusting a green run.
