import {
  formatReports,
  LAYOUT_VIEWPORTS,
  loadKnownFindings,
  partitionFindings,
  prepareLayoutProbe,
  sweepLayout,
} from '../../fixtures/layout';
import { test, expect, loginAdmin, visitAndWaitForHydration } from '../../fixtures';
import { AUDIT_ROUTE_COUNT, resolveAuditRoutes, type AuditRoute } from '../../helpers/audit-routes';

/**
 * Every audit route, measured at 375x667 and 1440x900 on the same document, for overlapping
 * content and content painting outside its clip container. jsdom has no layout engine, so no
 * unit test can see this class of bug.
 *
 * Page content lives inside the #outlet_root scroll area, so the scroll walk is what reaches
 * anything below the first screen.
 *
 * No retries: a layout defect that shows only sometimes is still a defect, and a retry would
 * pass it.
 */
test.describe.configure({ retries: 0 });

// Module scope: a malformed quarantine row fails collection once, not once per route.
const KNOWN = loadKnownFindings();

let ROUTES: AuditRoute[];

test.beforeAll(async ({ browser }) => {
  ROUTES = await resolveAuditRoutes(browser);
});

test.describe('layout overlap audit (@cicd)', () => {
  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
  });

  for (let i = 0; i < AUDIT_ROUTE_COUNT; i++) {
    test(`route ${i} has no overlapping or escaping content`, async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      const route = ROUTES[i];
      await visitAndWaitForHydration(page, route.path);
      await prepareLayoutProbe(page);
      const expectedPath = new URL(page.url()).pathname;

      const reports = await sweepLayout(page, {
        viewports: LAYOUT_VIEWPORTS,
        states: ['scroll'],
        scrollFractions: [0.25, 0.5, 0.75, 1],
        budgetMs: 15_000,
      });
      const { fresh, matched, stale } = partitionFindings(reports, route.name, KNOWN);

      await testInfo.attach('layout-states', {
        contentType: 'application/json',
        body: JSON.stringify(reports.map((r) => ({ viewport: r.viewport, states: r.states })), null, 2),
      });
      await testInfo.attach('layout-ledger', {
        contentType: 'application/json',
        body: JSON.stringify(reports.map((r) => r.ledger), null, 2),
      });

      const totals = reports.reduce(
        (acc, r) => ({
          states: acc.states + r.states.length,
          unprobeable: acc.unprobeable + r.ledger.unprobeable,
          unsettled: acc.unsettled + r.ledger.statesUnsettled.length,
          skipped: acc.skipped + r.ledger.statesSkipped.length,
          scrollers: acc.scrollers + r.ledger.scrollContainers,
        }),
        { states: 0, unprobeable: 0, unsettled: 0, skipped: 0, scrollers: 0 },
      );
      testInfo.annotations.push({
        type: 'layout',
        description:
          `${route.name} states=${totals.states} unprobeable=${totals.unprobeable} ` +
          `unsettled=${totals.unsettled} skipped=${totals.skipped} scrollers=${totals.scrollers} ` +
          `known=${matched.length}`,
      });

      expect(
        stale,
        'stale quarantine entries no longer fire; delete them from ' +
          `frontend/tests/playwright/layout-known-findings.json:\n${stale
            .map((s) => `  ${s.viewport} ${s.state} ${s.kind} ${s.findingKey}  (${s.issue}, ${s.owner})`)
            .join('\n')}`,
      ).toEqual([]);

      expect(fresh, `${route.path}\n${formatReports(reports, matched)}`).toEqual([]);

      // A state that was skipped or never settled was never measured; passing on it would make
      // a blind run indistinguishable from a clean one. `unprobeable` is reported, not gated:
      // clipped table cells past the viewport edge are routine.
      for (const r of reports) {
        const vp = `${r.viewport.width}x${r.viewport.height}`;
        expect(r.ledger.statesUnsettled, `${vp}: states still loading when measured`).toEqual([]);
        expect(r.ledger.statesSkipped, `${vp}: states skipped over the time budget`).toEqual([]);
        expect(r.ledger.candidates, `${vp}: the base state measured no content`).toBeGreaterThan(0);
      }

      expect(new URL(page.url()).pathname, 'the sweep must not navigate away').toBe(expectedPath);
    });
  }
});
