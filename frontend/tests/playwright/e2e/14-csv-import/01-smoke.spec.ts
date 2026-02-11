/**
 * CSV Import Smoke Tests
 *
 * Tests the CSV import modal on the DEDICATED CSV Import Org.
 * This org is isolated from other test data (DTX, Test Organization).
 *
 * Infrastructure (created by populate_csv_import_data):
 * - CSV Import Org (pk=3) - dedicated org
 * - CSV Import League (steam_league_id=17931) - under CSV org
 * - CSV Import Tournament - empty, for tournament CSV import
 *
 * Test users (exist in DB, NOT in any org):
 * - csv_steam_user (pk=1040, steam=76561198800000001)
 * - csv_discord_user (pk=1041, discord=300000000000000001)
 * - csv_both_ids (pk=1042, steam+discord)
 * - csv_conflict_user (pk=1043, steam+discord mismatch)
 * - csv_team_user (pk=1044, steam=76561198800000005)
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API_URL = 'https://localhost/api';
const CSV_DIR = path.resolve(__dirname, '../../fixtures/csv');

// CSV Import Org name (must match populate_csv_import_data)
const CSV_ORG_NAME = 'CSV Import Org';
const CSV_TOURNAMENT_NAME = 'CSV Import Tournament';

let orgPk: number;
let tournamentPk: number;

test.describe('CSV Import - Org (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Find the dedicated CSV Import Org by name
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const csvOrg = orgs.find(
      (o: { name: string }) => o.name === CSV_ORG_NAME
    );
    if (!csvOrg) throw new Error(`${CSV_ORG_NAME} not found. Run just db::populate::all`);
    orgPk = csvOrg.pk;

    // Find the CSV Import Tournament
    const tournamentsResp = await context.request.get(`${API_URL}/tournaments/`);
    const tournaments = await tournamentsResp.json();
    const csvTournament = tournaments.find(
      (t: { name: string }) => t.name === CSV_TOURNAMENT_NAME
    );
    if (!csvTournament) throw new Error(`${CSV_TOURNAMENT_NAME} not found. Run just db::populate::all`);
    tournamentPk = csvTournament.pk;

    await context.close();
  });

  test.beforeEach(async ({ context, loginAdmin }) => {
    // Reset CSV import data to clean state before each test
    const resetResp = await context.request.post(`${API_URL}/tests/csv-import/reset/`);
    if (!resetResp.ok()) {
      throw new Error(`CSV reset failed: ${resetResp.status()}`);
    }
    await loginAdmin();
  });

  test('import button visible for admin', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await expect(page.getByTestId('org-csv-import-btn')).toBeVisible({ timeout: 10000 });
  });

  test('opens modal and shows drag area', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await page.getByTestId('org-csv-import-btn').click();
    await expect(page.getByRole('heading', { name: 'Import CSV' })).toBeVisible();
    await expect(page.getByText('Drop a CSV file here')).toBeVisible();
  });

  test('@cicd imports valid CSV with known test users', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await page.getByTestId('org-csv-import-btn').click();

    // Upload the valid-import.csv fixture (3 known test users)
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByText('Drop a CSV file here').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(path.join(CSV_DIR, 'valid-import.csv'));

    // Preview should show 3 valid rows
    await expect(page.getByText('3 valid')).toBeVisible({ timeout: 5000 });

    // Import
    await page.getByRole('button', { name: /Import 3 row/ }).click();

    // Results summary
    await expect(page.getByText('Added', { exact: true })).toBeVisible({ timeout: 10000 });
  });

  test('shows validation errors for bad rows', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await page.getByTestId('org-csv-import-btn').click();

    // Upload the errors-import.csv fixture (2 valid + 2 errors)
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByText('Drop a CSV file here').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(path.join(CSV_DIR, 'errors-import.csv'));

    // Should show both valid and error counts
    await expect(page.getByText('2 valid')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('2 errors')).toBeVisible({ timeout: 5000 });
  });

  test('creates stub users for unknown Steam IDs', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}/?tab=users`);
    await page.getByTestId('org-csv-import-btn').click();

    // Upload stubs-import.csv (3 unknown Steam IDs → creates stubs)
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByText('Drop a CSV file here').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(path.join(CSV_DIR, 'stubs-import.csv'));

    await expect(page.getByText('3 valid')).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: /Import 3 row/ }).click();

    // All 3 should be added with stubs created
    await expect(page.getByText('Added', { exact: true })).toBeVisible({ timeout: 10000 });
  });
});

test.describe('CSV Import - Tournament', () => {
  test.beforeAll(async ({ browser }) => {
    // Reuse the orgPk/tournamentPk from the org describe block
    // If running independently, need to fetch again
    if (!orgPk || !tournamentPk) {
      const context = await browser.newContext({ ignoreHTTPSErrors: true });
      const orgsResp = await context.request.get(`${API_URL}/organizations/`);
      const orgs = await orgsResp.json();
      const csvOrg = orgs.find(
        (o: { name: string }) => o.name === CSV_ORG_NAME
      );
      if (csvOrg) orgPk = csvOrg.pk;

      const tournamentsResp = await context.request.get(`${API_URL}/tournaments/`);
      const tournaments = await tournamentsResp.json();
      const csvTournament = tournaments.find(
        (t: { name: string }) => t.name === CSV_TOURNAMENT_NAME
      );
      if (csvTournament) tournamentPk = csvTournament.pk;
      await context.close();
    }
  });

  test.beforeEach(async ({ context, loginAdmin }) => {
    // Reset CSV import data to clean state before each test
    const resetResp = await context.request.post(`${API_URL}/tests/csv-import/reset/`);
    if (!resetResp.ok()) {
      throw new Error(`CSV reset failed: ${resetResp.status()}`);
    }
    await loginAdmin();
  });

  test('tournament import button visible', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/?tab=players`);
    await expect(page.getByTestId('tournament-csv-import-btn')).toBeVisible({ timeout: 10000 });
  });

  test('imports CSV with team names into tournament', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/?tab=players`);
    await page.getByTestId('tournament-csv-import-btn').click();

    // Upload teams-import.csv (4 users with team assignments)
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByText('Drop a CSV file here').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(path.join(CSV_DIR, 'teams-import.csv'));

    await expect(page.getByText('4 valid')).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: /Import 4 row/ }).click();

    // Results
    await expect(page.getByText('Added', { exact: true })).toBeVisible({ timeout: 10000 });
  });
});
