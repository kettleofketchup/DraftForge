import type { Browser } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';
import {
  resetSignupRecordsExport,
  type SignupRecordsExportData,
} from '../../fixtures/signup-records-export';

const CSV_HEADER = [
  'event_id',
  'event_name',
  'scheduled_at',
  'event_state',
  'series_id',
  'user_id',
  'discord_id',
  'original_signed_up_at',
  'original_commitment',
  'original_rsvp_class',
  'original_means',
  'final_status',
  'final_commitment',
  'final_rsvp_class',
  'final_signed_up_at',
  'final_line_seq',
  'withdrawn_at',
  'change_count',
  'last_changed_at',
].join(',');

let data: SignupRecordsExportData;

async function reset(browser: Browser): Promise<SignupRecordsExportData> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    return await resetSignupRecordsExport(context.request);
  } finally {
    await context.close();
  }
}

test.describe('Sign-up records export and retention @cicd', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ browser }) => {
    data = await reset(browser);
  });

  test.afterAll(async ({ browser }) => {
    await reset(browser);
  });

  test('staff downloads a CSV that includes a deleted event', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.staff_pk);
    await visitAndWaitForHydration(page, `/organizations/${data.org_pk}`);
    await page.getByTestId('export-signup-records-button').click();
    await expect(
      page.getByTestId('export-signup-records-dialog'),
    ).toBeVisible();

    const downloading = page.waitForEvent('download');
    await page.getByTestId('export-signup-records-submit').click();
    const download = await downloading;
    expect(download.suggestedFilename()).toMatch(
      new RegExp(`^signup-records-${data.org_pk}-\\d{8}\\.csv$`),
    );
    const path = await download.path();
    const lines = (await readFile(path, 'utf-8'))
      .split(/\r?\n/)
      .filter((line) => line.length > 0);
    expect(lines[0]).toBe(CSV_HEADER);
    const deleted = lines.filter(
      (line) =>
        line.startsWith(`${data.deleted_event_pk},`) &&
        line.includes(',deleted,'),
    );
    expect(deleted).toHaveLength(3);
    expect(deleted[0]).toContain(data.deleted_event_name);
    expect(
      lines.filter((line) => line.startsWith(`${data.cancelled_event_pk},`)),
    ).toHaveLength(3);
    await expect(page.getByTestId('export-signup-records-dialog')).toHaveCount(
      0,
    );
  });

  test('member does not see the export button', async ({ context, page }) => {
    await loginAsUser(context, data.member_pk);
    await visitAndWaitForHydration(page, `/organizations/${data.org_pk}`);
    await expect(page.getByTestId('org-tab-leagues')).toBeVisible();
    await expect(page.getByTestId('export-signup-records-button')).toHaveCount(
      0,
    );
  });

  test('admin saves retention and is stopped below the minimum', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.admin_pk);
    const settingsUrl = `/organizations/${data.org_pk}/settings/`;
    const patches: string[] = [];
    page.on('request', (req) => {
      if (req.method() === 'PATCH' && req.url().includes(settingsUrl)) {
        patches.push(req.url());
      }
    });

    await visitAndWaitForHydration(
      page,
      `/organizations/${data.org_pk}?settings=signup-records`,
    );
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    const section = page.getByTestId('org-settings-signup-records');
    await expect(page.getByTestId('signup-retention-forever')).toBeChecked();
    await page.getByTestId('signup-retention-period').click();
    const days = page.getByTestId('signup-retention-days');
    await days.fill('365');

    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' && resp.url().includes(settingsUrl),
    );
    await page.getByTestId('org-settings-save').click();
    const response = await saved;
    expect(response.status()).toBe(200);
    expect((await response.json()).signup_record_retention_days).toBe(365);
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);

    await page.reload();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await page.getByTestId('org-settings-tab-signup-records').click();
    await expect(page.getByTestId('signup-retention-period')).toBeChecked();
    await expect(days).toHaveValue('365');

    const before = patches.length;
    await days.fill('10');
    await page.getByTestId('org-settings-save').click();
    await expect(
      section.getByText('Minimum 30 days.', { exact: true }),
    ).toBeVisible();
    expect(patches).toHaveLength(before);
  });
});
