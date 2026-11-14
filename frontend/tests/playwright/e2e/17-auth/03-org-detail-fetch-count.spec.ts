/**
 * Org detail (GET /api/organizations/<pk>/) is fetched once per page load
 * for every role, and switching tabs (a ?tab= search-param change) does not
 * refetch it. The anonymous ?tab=users case also covers the page bouncing a
 * viewer off a tab it may not see.
 */

import { roleMatrixTest as test, expect, ROLE_NAMES, type RoleName } from '../../fixtures';
import type { Page } from '@playwright/test';

const AUTH_MATRIX_ORG_PK = 8;
const ORG_DETAIL = new RegExp(`/api/organizations/${AUTH_MATRIX_ORG_PK}/?(\\?.*)?$`);

function countOrgDetail(page: Page): () => number {
  let n = 0;
  page.on('request', (r) => {
    if (r.method() === 'GET' && ORG_DETAIL.test(r.url())) n++;
  });
  return () => n;
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('org-tab-leagues')).toBeVisible({ timeout: 15000 });
  await page.waitForLoadState('networkidle');
}

async function forEachRole(
  roleContexts: Record<RoleName, { page: Page }>,
  fn: (role: RoleName, page: Page) => Promise<void>,
): Promise<void> {
  await Promise.all(ROLE_NAMES.map((role) => fn(role, roleContexts[role].page)));
}

test.describe('Org detail fetch count (8 roles + anonymous in parallel)', () => {
  for (const query of ['', '?tab=events', '?tab=users']) {
    test(`one org-detail fetch per load (/organizations/${AUTH_MATRIX_ORG_PK}${query})`, async ({
      roleContexts,
    }) => {
      await forEachRole(roleContexts, async (role, page) => {
        const count = countOrgDetail(page);
        await page.goto(`/organizations/${AUTH_MATRIX_ORG_PK}${query}`);
        await settle(page);
        expect(count(), `${role} org-detail fetches`).toBe(1);
      });
    });
  }

  test('switching tabs does not refetch org detail', async ({ roleContexts }) => {
    await forEachRole(roleContexts, async (role, page) => {
      const count = countOrgDetail(page);
      await page.goto(`/organizations/${AUTH_MATRIX_ORG_PK}`);
      await settle(page);
      for (const tab of ['events', 'leagues', 'events']) {
        await page.getByTestId(`org-tab-${tab}`).click();
        await expect(page.getByTestId(`org-tab-${tab}`)).toHaveAttribute('data-state', 'active');
        await page.waitForLoadState('networkidle');
      }
      expect(count(), `${role} org-detail fetches after tab switches`).toBe(1);
    });
  });
});
