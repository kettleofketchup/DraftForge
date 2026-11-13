import type { BrowserContext, Page } from '@playwright/test';

import {
  expect,
  getEventsTestData,
  loginAdmin,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { getCsrfToken } from '../../fixtures/events';

// Each test creates its own throwaway league so deleting it cannot affect
// seeded data used by other specs.
async function createLeague(context: BrowserContext, name: string): Promise<number> {
  const eventInfo = await getEventsTestData(context);
  const parent = await (await context.request.get(`/api/leagues/${eventInfo.eventsLeaguePk}/`)).json();
  const orgPk = typeof parent.organization === 'object' ? parent.organization.pk : parent.organization;
  const resp = await postWithCsrf(context, '/api/leagues/', { name, organization: orgPk });
  expect(resp.status(), await resp.text()).toBe(201);
  return (await resp.json()).pk;
}

async function cleanup(context: BrowserContext, pk: number) {
  await context.request.delete(`/api/leagues/${pk}/`, {
    headers: { 'X-CSRFToken': await getCsrfToken(context) },
  });
}

async function openDeleteDialog(page: Page, pk: number, name: string) {
  await visitAndWaitForHydration(page, `/leagues/${pk}`);
  await page.getByTestId('edit-league-button').click();
  await page.getByTestId('open-delete-league-dialog').click();
  await expect(page.getByTestId('delete-league-dialog')).toBeVisible();
  await page.getByTestId('delete-league-confirm-input').fill(name);
}

async function expectDeleted(page: Page, context: BrowserContext, pk: number, patches: string[]) {
  await expect(
    page.locator('[data-sonner-toast][data-type="success"]').filter({ hasText: /deleted/i }),
  ).toBeVisible();
  expect(patches).toEqual([]);
  expect((await context.request.get(`/api/leagues/${pk}/`)).status()).toBe(404);
}

test.describe('Delete league @cicd', () => {
  for (const how of ['click', 'enter'] as const) {
    test(`deletes the league when confirmed by ${how}`, async ({ page, context }) => {
      await loginAdmin(context);
      const name = `Delete Me ${how} ${Date.now()}`;
      const pk = await createLeague(context, name);
      try {
        const patches: string[] = [];
        page.on('request', (req) => {
          if (req.method() === 'PATCH' && req.url().includes('/api/leagues/')) patches.push(req.url());
        });

        await openDeleteDialog(page, pk, name);
        if (how === 'click') {
          await page.getByTestId('delete-league-confirm').click();
        } else {
          await page.getByTestId('delete-league-confirm-input').press('Enter');
        }

        await expectDeleted(page, context, pk, patches);
      } finally {
        await cleanup(context, pk);
      }
    });
  }
});
