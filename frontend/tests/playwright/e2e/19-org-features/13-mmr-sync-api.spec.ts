import type { BrowserContext, Page } from '@playwright/test';

import {
  expect,
  loginAdmin,
  loginMmrSync,
  mmrSyncRequest,
  orgFeaturesApi,
  resetMmrSync,
  test,
  visitAndWaitForHydration,
  type MmrSyncTestData,
} from '../../fixtures';

interface CreatedToken {
  id: number;
  prefix: string;
  token: string;
}

const TOKEN_FORMAT = /^dfk_[0-9a-f]+_\S+$/;

async function openApiAccess(page: Page, orgPk: number): Promise<void> {
  await visitAndWaitForHydration(
    page,
    `/organizations/${orgPk}?settings=api-access`,
  );
  await expect(page.getByTestId('org-settings-modal')).toBeVisible();
  await expect(page.getByTestId('org-settings-api-access')).toBeVisible();
}

async function expectNoApiAccess(page: Page, orgPk: number): Promise<void> {
  await visitAndWaitForHydration(
    page,
    `/organizations/${orgPk}?settings=api-access`,
  );
  await expect(page.getByTestId('org-tab-leagues')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('org-settings-tab-api-access')).toHaveCount(0);
  await expect(page.getByTestId('org-settings-api-access')).toHaveCount(0);
}

async function createTokenViaApi(
  context: BrowserContext,
  orgPk: number,
  name: string,
): Promise<CreatedToken> {
  return orgFeaturesApi<CreatedToken>(
    context,
    'POST',
    `/organizations/${orgPk}/api-tokens/`,
    { name },
  );
}

test.describe('Org features: MMR sync API @cicd', () => {
  let data: MmrSyncTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetMmrSync(request);
  });

  test('site admin unlocks MMR sync API and the org admin gets API access @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.locked.pk;
    await loginMmrSync(context, 'locked_admin');
    await expectNoApiAccess(page, pk);

    await loginAdmin(context);
    await visitAndWaitForHydration(page, `/organizations/${pk}`);
    const row = page.getByTestId('locked-feature-row-mmr_sync');
    await row.scrollIntoViewIfNeeded();
    await expect(row).toContainText('MMR sync API');
    const toggle = page.getByTestId('locked-feature-switch-mmr_sync');
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PUT' &&
        resp.url().includes(`/organizations/${pk}/features/`),
    );
    await page.getByTestId('locked-feature-save-mmr_sync').click();
    expect((await saved).status()).toBe(200);

    await page.reload();
    await expect(
      page.getByTestId('locked-feature-switch-mmr_sync'),
    ).toHaveAttribute('aria-checked', 'true');

    await loginMmrSync(context, 'locked_admin');
    await openApiAccess(page, pk);
    await expect(page.getByTestId('api-access-locked')).toHaveCount(0);
    await expect(page.getByTestId('api-token-create')).toBeEnabled();
  });

  test('org admin with MMR sync API on sees the API access section @cicd', async ({
    page,
    context,
  }) => {
    await loginMmrSync(context, 'admin');
    await openApiAccess(page, data.orgs.unlocked.pk);
    await expect(page.getByTestId('org-settings-tab-api-access')).toBeVisible();
    await expect(page.getByTestId('api-access-locked')).toHaveCount(0);
    await expect(page.getByTestId('api-token-create')).toBeEnabled();
  });

  test('org staff and members cannot reach API access @cicd', async ({
    page,
    context,
  }) => {
    for (const role of ['staff', 'member'] as const) {
      await loginMmrSync(context, role);
      await expectNoApiAccess(page, data.orgs.unlocked.pk);
      await expect(page.getByTestId('org-settings-button')).toHaveCount(0);
      await expect(page.getByTestId('org-settings-modal')).toHaveCount(0);
    }
  });

  test('org admin with MMR sync API off sees no API access section @cicd', async ({
    page,
    context,
  }) => {
    await loginMmrSync(context, 'locked_admin');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.locked.pk}`,
    );
    await page.getByTestId('org-settings-button').click();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(
      page.getByTestId('org-settings-tab-staff-placement'),
    ).toBeVisible();
    await expect(page.getByTestId('org-settings-tab-api-access')).toHaveCount(
      0,
    );

    await expectNoApiAccess(page, data.orgs.locked.pk);
  });

  test('org admin creates a token and sees the secret only once @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.unlocked.pk;
    await loginMmrSync(context, 'admin');
    await openApiAccess(page, pk);

    await page.getByTestId('api-token-create').click();
    await expect(page.getByTestId('api-token-create-dialog')).toBeVisible();
    await page.getByTestId('api-token-name').fill('Rank bot');
    const createdResp = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes(`/organizations/${pk}/api-tokens/`),
    );
    await page.getByTestId('api-token-create-submit').click();
    const resp = await createdResp;
    expect(resp.status()).toBe(201);
    const created = (await resp.json()) as CreatedToken;

    const secret = page.getByTestId('api-token-secret');
    await expect(secret).toBeVisible();
    await expect(secret).toHaveText(TOKEN_FORMAT);
    await expect(secret).toHaveText(created.token);
    await expect(secret).toContainText(`dfk_${created.prefix}_`);
    await expect(page.getByTestId('api-token-once-note')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('api-token-created-dialog')).toHaveCount(0);
    await expect(page.getByTestId('api-token-secret')).toHaveCount(0);

    const row = page.getByTestId(`api-token-row-${created.id}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText('Rank bot');
    await expect(
      page.getByTestId(`api-token-prefix-${created.id}`),
    ).toContainText(`dfk_${created.prefix}_`);
    await expect(page.getByTestId(`api-token-status-${created.id}`)).toHaveText(
      'Active',
    );
    const secretPart = created.token.split('_').slice(2).join('_');
    await expect(row).not.toContainText(secretPart);

    await page.reload();
    await expect(page.getByTestId(`api-token-row-${created.id}`)).toBeVisible();
    await expect(page.getByTestId('org-settings-api-access')).not.toContainText(
      secretPart,
    );
  });

  test('org admin revokes a token and it stops working @cicd', async ({
    page,
    context,
    request,
  }) => {
    const pk = data.orgs.unlocked.pk;
    await loginMmrSync(context, 'admin');
    const created = await createTokenViaApi(context, pk, 'Revoke me');
    expect((await mmrSyncRequest(request, pk, created.token)).status()).toBe(
      200,
    );

    await openApiAccess(page, pk);
    await expect(page.getByTestId(`api-token-status-${created.id}`)).toHaveText(
      'Active',
    );
    await page.getByTestId(`api-token-revoke-${created.id}`).click();
    const revoked = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'DELETE' &&
        resp.url().includes(`/api-tokens/${created.id}/`),
    );
    await page.getByTestId('api-token-revoke-confirm').click();
    expect((await revoked).status()).toBe(200);

    await expect(page.getByTestId(`api-token-status-${created.id}`)).toHaveText(
      'Revoked',
    );
    await expect(
      page.getByTestId(`api-token-revoke-${created.id}`),
    ).toHaveCount(0);
    expect((await mmrSyncRequest(request, pk, created.token)).status()).toBe(
      401,
    );
  });

  test('token requests show up in the usage table @cicd', async ({
    page,
    context,
    request,
  }) => {
    const pk = data.orgs.unlocked.pk;
    const adminPk = data.users.admin.pk;
    await loginMmrSync(context, 'admin');
    const created = await createTokenViaApi(context, pk, 'Usage bot');
    for (let i = 0; i < 3; i++) {
      expect((await mmrSyncRequest(request, pk, created.token)).status()).toBe(
        200,
      );
    }

    await openApiAccess(page, pk);
    await expect(page.getByTestId('api-usage-table')).toBeVisible();
    await expect(page.getByTestId(`api-usage-row-${adminPk}`)).toBeVisible();
    await expect(page.getByTestId(`api-usage-requests-${adminPk}`)).toHaveText(
      '3',
    );
  });

  test('org admin sees the rate limits read-only @cicd', async ({
    page,
    context,
  }) => {
    await loginMmrSync(context, 'admin');
    await openApiAccess(page, data.orgs.unlocked.pk);
    await expect(page.getByTestId('api-limits')).toBeVisible();
    await expect(page.getByTestId('api-limits-per-minute')).toHaveText('60');
    await expect(page.getByTestId('api-limits-per-day')).toHaveText('5,000');
    await expect(page.getByTestId('api-limits-form')).toHaveCount(0);
  });

  test('site admin edits the rate limits and they persist @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.unlocked.pk;
    await loginAdmin(context);
    await openApiAccess(page, pk);

    await expect(page.getByTestId('api-limits-form')).toBeVisible();
    await expect(page.getByTestId('api-limits')).toHaveCount(0);
    const perMinute = page.getByTestId('api-limits-per_minute');
    const perDay = page.getByTestId('api-limits-per_day');
    await expect(perMinute).toHaveValue('60');
    await expect(perDay).toHaveValue('5000');
    await perMinute.fill('25');
    await perDay.fill('1200');
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PUT' &&
        resp.url().includes(`/organizations/${pk}/api-limits/`),
    );
    await page.getByTestId('api-limits-save').click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('api-limits-save')).toBeDisabled();

    await page.reload();
    await expect(page.getByTestId('org-settings-api-access')).toBeVisible();
    await expect(page.getByTestId('api-limits-per_minute')).toHaveValue('25');
    await expect(page.getByTestId('api-limits-per_day')).toHaveValue('1200');

    await loginMmrSync(context, 'admin');
    await openApiAccess(page, pk);
    await expect(page.getByTestId('api-limits-per-minute')).toHaveText('25');
    await expect(page.getByTestId('api-limits-per-day')).toHaveText('1,200');
  });

  test('a token POST updates a member MMR by steam_id @cicd', async ({
    context,
    request,
  }) => {
    const pk = data.orgs.unlocked.pk;
    await loginMmrSync(context, 'admin');
    const created = await createTokenViaApi(context, pk, 'Sync bot');

    const resp = await mmrSyncRequest(request, pk, created.token, {
      game_type: 1,
      entries: [{ steam_id: data.player.steam_id, mmr: 4200 }],
    });
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toEqual({
      updated: 1,
      unchanged: 0,
      unmatched: [],
      invalid: [],
    });

    const members = await mmrSyncRequest(request, pk, created.token);
    expect(members.status()).toBe(200);
    const body = (await members.json()) as {
      members: {
        user_id: number;
        steam_id: number | null;
        mmr: number | null;
      }[];
    };
    expect(body.members).toContainEqual(
      expect.objectContaining({
        user_id: data.player.pk,
        steam_id: data.player.steam_id,
        mmr: 4200,
      }),
    );
  });
});
