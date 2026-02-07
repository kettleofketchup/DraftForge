/**
 * CSV Import Smoke Tests
 *
 * Tests the CSV import modal on the organization page:
 * - Button visibility for admins
 * - Modal opens with drag/drop area
 * - Valid CSV file import flow
 * - Error display for invalid CSV rows
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getFirstLeague,
} from '../../fixtures';
import path from 'path';
import fs from 'fs';
import os from 'os';

const API_URL = 'https://localhost/api';

let orgPk: number;

test.describe('CSV Import - Org', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Get first league to find org PK
    const league = await getFirstLeague(context);
    if (!league) throw new Error('No leagues found. Run just db::populate::all');

    const leagueResp = await context.request.get(`${API_URL}/leagues/${league.pk}/`);
    const leagueData = await leagueResp.json();
    orgPk = typeof leagueData.organization === 'object'
      ? leagueData.organization.pk
      : leagueData.organization;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('import button visible for admin', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await expect(page.getByTestId('org-csv-import-btn')).toBeVisible({ timeout: 10000 });
  });

  test('opens modal and shows drag area', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await page.getByTestId('org-csv-import-btn').click();
    await expect(page.getByText('Import CSV')).toBeVisible();
    await expect(page.getByText('Drop a CSV file here')).toBeVisible();
  });

  test('imports valid CSV file', async ({ page }) => {
    const csvContent = 'steam_friend_id,base_mmr\n76561198099999999,3000\n';
    const csvPath = path.join(os.tmpdir(), `test-import-${Date.now()}.csv`);
    fs.writeFileSync(csvPath, csvContent);

    try {
      await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
      await page.getByTestId('org-csv-import-btn').click();

      // Upload file via file chooser
      const fileChooserPromise = page.waitForEvent('filechooser');
      await page.getByText('Drop a CSV file here').click();
      const fileChooser = await fileChooserPromise;
      await fileChooser.setFiles(csvPath);

      // Should show preview
      await expect(page.getByText('1 valid')).toBeVisible({ timeout: 5000 });

      // Click import
      await page.getByRole('button', { name: /Import 1 row/ }).click();

      // Should show results
      await expect(page.getByText('Added')).toBeVisible({ timeout: 10000 });
    } finally {
      fs.unlinkSync(csvPath);
    }
  });

  test('shows error for invalid CSV rows', async ({ page }) => {
    const csvContent = 'base_mmr\n5000\n';
    const csvPath = path.join(os.tmpdir(), `test-invalid-${Date.now()}.csv`);
    fs.writeFileSync(csvPath, csvContent);

    try {
      await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
      await page.getByTestId('org-csv-import-btn').click();

      const fileChooserPromise = page.waitForEvent('filechooser');
      await page.getByText('Drop a CSV file here').click();
      const fileChooser = await fileChooserPromise;
      await fileChooser.setFiles(csvPath);

      // Should show error count
      await expect(page.getByText('1 errors')).toBeVisible({ timeout: 5000 });
    } finally {
      fs.unlinkSync(csvPath);
    }
  });
});
