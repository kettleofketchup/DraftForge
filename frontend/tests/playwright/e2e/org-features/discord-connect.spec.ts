import type { BrowserContext, Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  patchWithCsrf,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const DISCORD_AUTHORIZE_URL =
  'https://discord.com/oauth2/authorize?client_id=1&state=x';
const TEST_SERVER_ID = '123456789012345678';

interface BotStatus {
  has_bot: boolean;
  reason: 'no_server_configured' | null;
  guild_name: string | null;
}

async function mockBotStatus(
  page: Page,
  orgPk: number,
  status: BotStatus,
): Promise<void> {
  await page.route(
    `**/api/discord/organizations/${orgPk}/bot-status/`,
    (route) => route.fulfill({ json: status }),
  );
}

async function setServerId(
  context: BrowserContext,
  orgPk: number,
  serverId: string | null,
): Promise<void> {
  const resp = await patchWithCsrf(
    context,
    `${API_URL}/organizations/${orgPk}/`,
    {
      discord_server_id: serverId,
    },
  );
  expect(resp.ok()).toBe(true);
}

function toast(page: Page, type: 'success' | 'error', text: string) {
  return page
    .locator(`[data-sonner-toast][data-type="${type}"]`)
    .filter({ hasText: text });
}

test.describe('Org features: connect Discord @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await loginOrgFeatures(context, 'admin');
  });

  test('admin without a server is sent to the Discord install page @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await page.route(
      `**/api/discord/organizations/${pk}/install-link/`,
      (route) => route.fulfill({ json: { url: DISCORD_AUTHORIZE_URL } }),
    );
    await page.route('https://discord.com/**', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: '<html><body>Discord stub</body></html>',
      }),
    );
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=discord`,
    );

    const card = page.getByTestId('org-discord-connection');
    await expect(card).toBeVisible();
    await expect(page.getByTestId('org-discord-not-connected')).toBeVisible();
    const button = page.getByTestId('org-discord-connect-button');
    await expect(button).toHaveText('Connect Discord server');
    await expect(button).toBeEnabled();

    await button.click();
    await expect(page).toHaveURL(DISCORD_AUTHORIZE_URL);
  });

  test('admin with the bot in a server sees the server name @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await mockBotStatus(page, pk, {
      has_bot: true,
      reason: null,
      guild_name: 'Test Guild',
    });
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=discord`,
    );

    await expect(page.getByTestId('org-discord-connected')).toHaveText(
      'Connected to Test Guild',
    );
    await expect(page.getByTestId('org-discord-connect-button')).toHaveText(
      'Switch server',
    );
    await expect(page.getByTestId('org-discord-not-connected')).toHaveCount(0);
  });

  test.describe('server ID set by hand', () => {
    // The private org keeps the server ID off the org other specs share.
    test.afterEach(async ({ context }) => {
      await setServerId(context, data.orgs.private.pk, null);
    });

    test('admin who saves a server ID without the bot is told to add it @cicd', async ({
      page,
    }) => {
      const pk = data.orgs.private.pk;
      await mockBotStatus(page, pk, {
        has_bot: false,
        reason: null,
        guild_name: null,
      });
      await visitAndWaitForHydration(
        page,
        `/organizations/${pk}?settings=discord`,
      );
      await expect(page.getByTestId('org-discord-not-connected')).toBeVisible();

      await page
        .getByTestId('org-discord-server-id-input')
        .fill(TEST_SERVER_ID);
      const saved = page.waitForResponse(
        (resp) =>
          resp.request().method() === 'PATCH' &&
          resp.url().endsWith(`/organizations/${pk}/`),
      );
      await page.getByTestId('org-settings-save').click();
      expect((await saved).ok()).toBe(true);

      await expect(page.getByTestId('org-discord-bot-missing')).toBeVisible();
      await expect(page.getByTestId('org-discord-connect-button')).toHaveText(
        'Add bot to server',
      );
      await expect(
        page.getByTestId('org-discord-connect-button'),
      ).toBeEnabled();
    });
  });

  test('unsaved settings disable the connect button @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=discord`,
    );
    const card = page.getByTestId('org-discord-connection');
    const button = page.getByTestId('org-discord-connect-button');
    await expect(button).toBeEnabled();
    await expect(card).not.toContainText('Save or discard your changes first.');

    await page
      .getByTestId('org-discord-input')
      .fill('https://discord.gg/unsaved-edit');

    await expect(button).toBeDisabled();
    await expect(card).toContainText('Save or discard your changes first.');
  });

  test('admin opens the Discord settings from the org header @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(page, `/organizations/${pk}`);

    const headerButton = page.getByTestId('org-connect-discord-button');
    await expect(headerButton).toHaveText('Connect Discord');
    await headerButton.click();

    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(page.getByTestId('org-settings-tab-discord')).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page).toHaveURL(/settings=discord/);
    await expect(page.getByTestId('org-discord-connection')).toBeVisible();
  });

  for (const role of ['staff', 'member'] as const) {
    test(`org ${role} sees no connect Discord button @cicd`, async ({
      page,
      context,
    }) => {
      await loginOrgFeatures(context, role);
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}`,
      );
      await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
        'data-state',
        'active',
      );
      await expect(page.getByTestId('org-connect-discord-button')).toHaveCount(
        0,
      );
    });
  }

  test('install callback success toasts and clears the result params @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=discord&discord=connected`,
    );

    await expect(
      toast(page, 'success', 'Discord server connected'),
    ).toBeVisible();
    await expect(page).not.toHaveURL(/discord=/);
    await expect(page).toHaveURL(/settings=discord/);
    await expect(page.getByTestId('org-discord-connection')).toBeVisible();
  });

  test('install callback error toasts the reason @cicd', async ({ page }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=discord&discord=error&reason=bot_missing`,
    );

    await expect(
      toast(page, 'error', "The DraftForge bot couldn't see that server."),
    ).toBeVisible();
    await expect(page).not.toHaveURL(/discord=|reason=/);
    await expect(page).toHaveURL(/settings=discord/);
  });

  test('install callback with a tampered state redirects as expired @cicd', async ({
    context,
  }) => {
    const resp = await context.request.get(
      `${API_URL}/discord/install/callback/?state=bad`,
      { maxRedirects: 0 },
    );
    expect(resp.status()).toBe(302);
    const location = new URL(resp.headers()['location'], API_URL);
    expect(location.pathname).toBe('/organizations');
    expect(location.searchParams.get('discord')).toBe('error');
    expect(location.searchParams.get('reason')).toBe('expired');
  });
});
