import {
  test,
  expect,
  visitAndWaitForHydration,
  loginAdmin,
} from '../../fixtures';
import {
  AUDIT_ROUTE_COUNT,
  resolveAuditRoutes,
  type AuditRoute,
} from '../../helpers/audit-routes';
import { findOverflow } from '../../../../scripts/find-overflow';

let ROUTES: AuditRoute[];

test.beforeAll(async ({ browser }) => {
  ROUTES = await resolveAuditRoutes(browser);
});

test.describe('mobile horizontal overflow audit (@cicd)', () => {
  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
  });

  for (let i = 0; i < AUDIT_ROUTE_COUNT; i++) {
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

  for (let i = 0; i < AUDIT_ROUTE_COUNT; i++) {
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
