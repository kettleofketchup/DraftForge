import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
  getEventsTestData,
  loginAdmin,
} from '../../fixtures';
import { findOverflow } from '../../../../scripts/find-overflow';

type Route = { path: string };

let ROUTES: Route[];

test.beforeAll(async ({ browser }) => {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const tournament = await getTournamentByKey(ctx, 'completed_bracket');
  if (!tournament) {
    throw new Error(
      "Tournament 'completed_bracket' not found. Run `just db::populate::all`.",
    );
  }
  const events = await getEventsTestData(ctx);
  await ctx.close();
  ROUTES = [
    { path: '/' },
    { path: '/events' },
    { path: `/events/${events.pk}` },
    { path: '/tournaments' },
    { path: `/tournament/${tournament.pk}/players` },
    { path: `/organizations/${events.orgPk}` },
    { path: '/leagues' },
    { path: '/user/1003' },
    { path: '/leagues/1' },
    { path: `/tournament/${tournament.pk}/bracket` },
    { path: `/events/${events.pk}/discord` },
  ];
});

test.describe('mobile horizontal overflow audit (@cicd)', () => {
  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
  });

  for (let i = 0; i < 11; i++) {
    test(`route ${i} has no horizontal overflow`, async ({ page }) => {
      const route = ROUTES[i];
      await visitAndWaitForHydration(page, route.path);
      const offenders = await page.evaluate(findOverflow);
      expect(
        offenders,
        `${route.path}\n${JSON.stringify(offenders, null, 2)}`,
      ).toEqual([]);
    });
  }
});

test.describe('mobile hydration mismatch audit (@cicd)', () => {
  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
  });

  for (let i = 0; i < 11; i++) {
    test(`route ${i} renders without SSR/client divergence`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));
      page.on('console', (m) => {
        if (m.type() === 'error') errors.push(m.text());
      });
      const route = ROUTES[i];
      await visitAndWaitForHydration(page, route.path);
      const HYDRATION_RX = /hydration|did not match|server rendered|server-rendered/i;
      const hydrationErrors = errors.filter((m) => HYDRATION_RX.test(m));
      expect(
        hydrationErrors,
        `${route.path}\n${JSON.stringify(hydrationErrors, null, 2)}`,
      ).toEqual([]);
    });
  }
});
