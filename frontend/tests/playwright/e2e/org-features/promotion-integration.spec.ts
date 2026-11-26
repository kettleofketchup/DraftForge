import type {
  APIRequestContext,
  BrowserContext,
  Locator,
  Page,
  Route,
} from '@playwright/test';
import {
  expect,
  leaderboardByUser,
  loginAdmin,
  loginOrgFeatures,
  orgFeaturesApi,
  postWithCsrf,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

// Synthetic external contacts only: no adaptor, contact log database or Discord
// call is made. Set PROMOTION_SCREENSHOT_DIR to also save each changed UI state
// at desktop and mobile size (<state>-<viewport>.png).
const SHOT_DIR = process.env.PROMOTION_SCREENSHOT_DIR;
const VIEWPORTS = [
  ['desktop', { width: 1440, height: 900 }],
  ['mobile', { width: 390, height: 844 }],
] as const;

async function shoot(page: Page, state: string, focus?: Locator) {
  if (!SHOT_DIR) return;
  for (const [name, size] of VIEWPORTS) {
    await page.setViewportSize(size);
    if (focus) await focus.scrollIntoViewIfNeeded();
    // Let the resized layout paint before capturing it.
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() =>
            requestAnimationFrame(() => resolve(null)),
          ),
        ),
    );
    await page.screenshot({
      path: `${SHOT_DIR}/${state}-${name}.png`,
      animations: 'disabled',
    });
  }
  await page.setViewportSize(VIEWPORTS[0][1]);
}

type Source = 'recent' | 'active' | 'discord';
type Ref = { pk: number | null; discord_id: string };

function rowId(ref: Ref): string {
  return ref.pk === null ? `discord-${ref.discord_id}` : String(ref.pk);
}

function candidatesResponse(page: Page, source: Source, hide?: boolean) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'GET' &&
      url.pathname.endsWith('/candidates/') &&
      url.searchParams.get('source') === source &&
      (hide === undefined ||
        url.searchParams.get('hide_messaged') === String(hide))
    );
  });
}

async function source(page: Page, value: Source): Promise<void> {
  const response = candidatesResponse(page, value);
  await page.getByTestId(`promo-source-${value}`).click();
  expect((await response).status()).toBe(200);
}

async function showMessaged(page: Page, value: Source): Promise<void> {
  const response = candidatesResponse(page, value, false);
  await page.getByTestId('promo-hide-messaged').click();
  expect((await response).status()).toBe(200);
}

async function expectTicked(page: Page, ref: Ref): Promise<void> {
  const id = rowId(ref);
  const tick = page.getByTestId(`promo-external-tick-${id}`);
  await expect(tick).toHaveAttribute('role', 'checkbox');
  await expect(tick).toHaveAttribute('aria-checked', 'true');
  await expect(tick).toHaveAttribute('aria-readonly', 'true');
  await expect(tick).toHaveAccessibleName('Contact recorded externally');
  await expect(page.getByTestId(`promo-external-contact-${id}`)).toContainText(
    'Delivery not verified',
  );
  // Message and Mark as sent stay off: an imported contact has no undo.
  await expect(
    page.getByTestId(`promo-candidate-message-${id}`),
  ).toBeDisabled();
  await expect(page.getByTestId(`promo-candidate-record-${id}`)).toBeDisabled();
}

function contactDateNy(at: Date): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
  }).format(at);
}

/** Post one guild-wide batch, as the adaptor would, holding a single invitation. */
async function importContact(
  request: APIRequestContext,
  token: string,
  orgPk: number,
  guildId: string,
  discordId: string,
  promoterDiscordId: string,
): Promise<void> {
  const recordedAt = new Date(Date.now() - 60_000);
  const imported = await request.post(
    `${API_URL}/organizations/${orgPk}/integration/v1/contact-receipts/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        source: 'contact_log',
        guild_id: guildId,
        scan_started_at: new Date().toISOString(),
        // Above the seeded contacts, so none of them is retracted.
        range: { after: '8104', through: '8199' },
        skipped_ids: [],
        entries: [
          {
            source_contact_id: '8199',
            target_discord_id: discordId,
            promoter_discord_id: promoterDiscordId,
            recorded_at: recordedAt.toISOString(),
            contact_date_ny: contactDateNy(recordedAt),
            contact_method: 'DISCORD_DM',
            contact_reason: 'EVENT_INVITE',
            occasion_id: '7001',
            event_date: null,
            forced: false,
          },
        ],
      },
    },
  );
  expect(imported.status()).toBe(200);
  const body = await imported.json();
  expect(body.applied).toBe(1);
  expect(body.credited).toBe(1);
  expect(body.results).toEqual([
    { index: 0, status: 'applied', point: 'credited', voided_local: false },
  ]);
}

test.describe('Promotion external contact history @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request, { externalContacts: true });
  });

  test.afterAll(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  async function open(page: Page): Promise<void> {
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=promotion&event=${data.events.upcoming.pk}`,
    );
    await expect(page.getByTestId('promo-source-recent')).toHaveAttribute(
      'data-state',
      'on',
    );
  }

  async function pickTemplate(page: Page): Promise<void> {
    const template = data.templates.find(
      (t) => t.org_pk === data.orgs.features.pk && t.name === 'First invite',
    )!;
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template.pk}`).click();
    await expect(page.getByTestId('promo-message-text')).not.toHaveValue('');
  }

  test('imported contacts are hidden by default, ticked read-only when shown, and block messaging', async ({
    page,
    context,
  }) => {
    const refs = data.external_contacts!;
    await loginOrgFeatures(context, 'promoter');
    await open(page);

    const warning = page.getByTestId('promo-contact-sync-warning');
    await expect(warning).toContainText('History may be incomplete');
    await expect(warning).toContainText('Last external receipt imported');
    await expect(warning).not.toContainText(/synced/i);
    await expect(
      page.getByTestId(`promo-candidate-row-${rowId(refs.non_member)}`),
    ).toHaveCount(0);
    await shoot(page, 'default-hidden', warning);

    await showMessaged(page, 'recent');
    await expectTicked(page, refs.non_member);
    const tick = page.getByTestId(
      `promo-external-tick-${rowId(refs.non_member)}`,
    );
    await tick.focus();
    await expect(tick).toBeFocused();
    await page.keyboard.press('Space');
    await expect(tick).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByTestId('promo-message-text')).toHaveCount(0);
    await shoot(
      page,
      'non-member',
      page.getByTestId(`promo-candidate-row-${rowId(refs.non_member)}`),
    );

    await source(page, 'active');
    await expectTicked(page, refs.external);
    await expect(
      page.getByTestId(`promo-last-messaged-${rowId(refs.external)}`),
    ).toHaveCount(0);
    await shoot(
      page,
      'shown-imported',
      page.getByTestId(`promo-candidate-row-${rowId(refs.external)}`),
    );

    const both = rowId(refs.local_and_external);
    await expectTicked(page, refs.local_and_external);
    await expect(page.getByTestId(`promo-last-messaged-${both}`)).toBeVisible();
    const row = page.getByTestId(`promo-candidate-row-${both}`);
    const undo = page.getByTestId(`promo-candidate-undo-${both}`);
    await expect(undo).toHaveCount(1);
    await shoot(page, 'local-and-external', row);

    const undone = page.waitForResponse(
      (r) => r.request().method() === 'DELETE' && r.url().includes('/sends/'),
    );
    await undo.click();
    const undoResponse = await undone;
    expect(undoResponse.status()).toBe(200);
    expect(await undoResponse.json()).toHaveProperty('writeback');
    await expect(page.getByTestId(`promo-last-messaged-${both}`)).toHaveCount(
      0,
    );
    await expectTicked(page, refs.local_and_external);
    await expect(undo).toHaveCount(0);
    await shoot(page, 'after-local-undo', row);

    await source(page, 'discord');
    await expectTicked(page, refs.discord_only);
    await expect(
      page.getByTestId(`promo-candidate-row-${rowId(refs.discord_only)}`),
    ).toContainText('No account yet');
    await shoot(
      page,
      'discord-only',
      page.getByTestId(`promo-candidate-row-${rowId(refs.discord_only)}`),
    );

    const refused = await postWithCsrf(
      context,
      `${API_URL}/organizations/${data.orgs.features.pk}/promotion/events/${data.events.upcoming.pk}/sends/`,
      { recipient_id: refs.external.pk, text: 'Hi there' },
    );
    expect(refused.status()).toBe(409);
    expect((await refused.json()).code).toBe('contact_already_recorded');
  });

  test('a contact imported while the tab is open drops the selected player on refetch', async ({
    page,
    context,
    browser,
    request,
  }) => {
    const admin: BrowserContext = await browser.newContext({
      ignoreHTTPSErrors: true,
    });
    await loginOrgFeatures(admin, 'admin');
    const created = await orgFeaturesApi<{ token: string }>(
      admin,
      'POST',
      `/organizations/${data.orgs.features.pk}/api-tokens/`,
      {
        name: 'Contact log adaptor e2e',
        operations: ['promotion:import'],
      },
    );
    await admin.close();

    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    const fresh = data.audiences!.fresh;
    await page.getByTestId(`promo-candidate-message-${fresh.pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toBeVisible();

    await importContact(
      request,
      created.token,
      data.orgs.features.pk,
      data.external_guild_id!,
      fresh.discord_id,
      data.external_contacts!.external.promoter_discord_id!,
    );
    // The open list polls every 30 seconds while the integration is set up.
    test.setTimeout(90_000);
    await expect(page.getByTestId('promo-message-text')).toHaveCount(0, {
      timeout: 65_000,
    });
    await expect(page.getByTestId('promo-pick-player')).toBeVisible();
    await expect(page.getByTestId('promo-message-dialog')).toHaveCount(0);
    await expect(
      page.getByTestId(`promo-candidate-row-${fresh.pk}`),
    ).toHaveCount(0);
    await shoot(
      page,
      'stale-tab-refresh',
      page.getByTestId('promo-contact-sync-warning'),
    );
  });

  test('a recorded send reports its external writeback state separately', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    const month = data.audiences!.month;
    await page.getByTestId(`promo-candidate-message-${month.pk}`).click();
    await pickTemplate(page);

    const banner = page.getByTestId('promo-sent-banner');
    const note = page.getByTestId('promo-external-writeback');
    const sending = page.waitForResponse(
      (r) => r.url().endsWith('/sends/') && r.request().method() === 'POST',
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    const sent = await sending;
    expect(sent.status()).toBe(201);
    expect((await sent.json()).writeback.state).toBe('pending');
    await expect(banner).toContainText('Sent to');
    await expect(note).toHaveAttribute('data-state', 'pending');
    await expect(note).toHaveText('Waiting to be recorded externally.');
    await shoot(page, 'send-pending', banner);

    // Later states come from the dispatcher; these responses are rewritten
    // in the browser (test-only simulation) to show their feedback.
    for (const [state, text, name] of [
      ['paused', /External recording is paused/, 'send-paused-simulated'],
      [
        'reconciliation_required',
        /needs review before it can be recorded externally/,
        'send-reconciliation-simulated',
      ],
      ['applied', /^Recorded externally\.$/, 'send-applied-simulated'],
    ] as const) {
      await banner.locator('[data-testid^="promo-undo-"]').click();
      await expect(banner).toHaveCount(0);
      await page.route('**/sends/', async (route: Route) => {
        const response = await route.fetch();
        const body = await response.json();
        body.writeback = { ...body.writeback, state };
        await route.fulfill({ response, json: body });
      });
      await page.getByTestId('promo-mark-sent-btn').click();
      await expect(note).toHaveAttribute('data-state', state);
      await expect(note).toHaveText(text);
      await expect(note).not.toContainText(/synced/i);
      await shoot(page, name, banner);
      await page.unroute('**/sends/');
    }
  });

  test('loading and outage keep the existing candidate states', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/candidates/?*', async (route) => {
      await held;
      await route.continue();
    });
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=promotion&event=${data.events.upcoming.pk}`,
    );
    await expect(page.getByTestId('promo-candidate-count')).toHaveText(
      'Loading players...',
    );
    await shoot(page, 'loading', page.getByTestId('promo-candidate-list'));
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    release();

    await page.route('**/candidates/?*', (route) =>
      route.fulfill({
        status: 503,
        json: { detail: 'Players are unavailable right now.' },
      }),
    );
    await page.reload();
    // The query retries before it gives up and shows the error.
    await expect(page.getByTestId('promo-candidates-error')).toHaveText(
      'Players are unavailable right now.',
      { timeout: 30_000 },
    );
    await shoot(page, 'error-outage', page.getByTestId('promo-candidate-list'));
  });

  test("the promoter's breakdown shows the external credit and the voided local point", async ({
    page,
    context,
  }) => {
    const pk = data.orgs.features.pk;
    await loginOrgFeatures(context, 'admin');
    const promoter = (await leaderboardByUser(context, pk)).get(
      data.users.promoter.pk,
    );
    expect(promoter).toBeDefined();
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?tab=contributions`,
    );
    await page
      .getByTestId(`contributions-row-${promoter!.org_user_pk}`)
      .click();
    const breakdown = page.getByTestId('contributions-breakdown');
    await expect(breakdown).toBeVisible();

    const entries = breakdown.locator('[data-testid^="contributions-entry-"]');
    const credit = entries.filter({
      hasText: 'Recorded in the external contact log',
    });
    await expect(credit).toHaveCount(1);
    await expect(credit).toContainText('Promotion message');
    await expect(credit).toContainText('+1');

    const voided = entries.filter({ hasText: 'Promotion point voided' });
    await expect(voided).toHaveCount(1);
    await expect(voided).toContainText(
      'Voided: the external contact log holds this point',
    );
    await expect(voided).toContainText('-1');
    await expect(voided).not.toContainText('+');
    await shoot(page, 'member-breakdown-void', breakdown);
  });

  test('a locked org keeps its existing promotion lockout', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'locked_admin');
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.locked.pk}?tab=promotion`,
    );
    await expect(page.getByTestId('org-tab-promotion')).toHaveCount(0);
    await expect(page.getByTestId('promo-contact-sync-warning')).toHaveCount(0);
    await shoot(page, 'locked-feature');
  });

  test('a site admin sees why tokens are locked when MMR sync and Promotion are off', async ({
    page,
    context,
  }) => {
    // The locked org has every feature off; only a site admin still sees the section.
    await loginAdmin(context);
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.locked.pk}?settings=api-access`,
    );
    const notice = page.getByTestId('api-access-locked');
    await expect(notice).toHaveText(
      'The MMR sync API and Promotion are both locked for this organization. Unlock one under Locked features before creating tokens.',
    );
    await expect(notice).not.toContainText(/contribution/i);
    await shoot(
      page,
      'api-access-locked',
      page.getByTestId('org-settings-api-access'),
    );
  });

  test('an org admin issues a promotion-scoped token from API access', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.features.pk;
    await loginOrgFeatures(context, 'admin');
    await page.setViewportSize(VIEWPORTS[0][1]);
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=api-access`,
    );
    const panel = page.getByTestId('org-settings-api-access');
    await expect(panel).toBeVisible();
    await expect(page.getByTestId('api-access-locked')).toHaveCount(0);
    await expect(panel).toContainText(
      'The adaptor needs the promotion operations',
    );
    await shoot(page, 'api-access-header', panel);

    await page.getByTestId('api-token-create').click();
    const dialog = page.getByTestId('api-token-create-dialog');
    await expect(dialog).toBeVisible();
    // New tokens default to the MMR pair; the adaptor token needs neither.
    for (const op of ['mmr:read', 'mmr:write']) {
      const toggle = page.getByTestId(`api-token-op-${op}`);
      await expect(toggle).toHaveAttribute('aria-checked', 'true');
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-checked', 'false');
    }
    await expect(
      page.getByTestId('api-token-op-contributions:read'),
    ).toHaveCount(0);
    // The recipients read and the totals export are gone.
    await expect(page.getByTestId('api-token-op-promotion:read')).toHaveCount(
      0,
    );
    const importToggle = page.getByTestId('api-token-op-promotion:import');
    await expect(importToggle).toHaveAttribute('aria-checked', 'false');
    await importToggle.click();
    await expect(importToggle).toHaveAttribute('aria-checked', 'true');
    await expect(dialog).toContainText(
      'Import external contact history and promotion points',
    );
    await expect(
      page.getByTestId('api-token-op-promotion:import-description'),
    ).toHaveText(
      'Records external contacts and awards and voids promotion points.',
    );
    await page.getByTestId('api-token-name').fill('Contact log adaptor');
    await shoot(page, 'api-access-create', dialog);

    const creating = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/organizations/${pk}/api-tokens/`),
    );
    await page.getByTestId('api-token-create-submit').click();
    const response = await creating;
    expect(response.status()).toBe(201);
    expect(response.request().postDataJSON()).toEqual({
      name: 'Contact log adaptor',
      operations: ['promotion:import'],
    });
    const created = (await response.json()) as {
      id: number;
      token: string;
      operations: string[];
    };
    expect(created.operations).toEqual(['promotion:import']);
    await expect(page.getByTestId('api-token-secret')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('api-token-secret')).toHaveCount(0);
    await expect(page.getByTestId('api-token-created-dialog')).toHaveCount(0);
    await expect(page.getByTestId('api-token-create-dialog')).toHaveCount(0);

    const ops = page.getByTestId(`api-token-operations-${created.id}`);
    await expect(ops).toHaveText(
      /Import external contact history and promotion points/,
    );
    await expect(ops).not.toContainText('recipients');
    // The name keeps a readable width next to the token and its operations,
    // and no cell's content is clipped or spills into its neighbour, at both
    // screenshot sizes.
    for (const [, size] of VIEWPORTS) {
      await page.setViewportSize(size);
      const name = page.getByTestId(`api-token-name-${created.id}`);
      await expect(name).toHaveText('Contact log adaptor');
      const box = await name.boundingBox();
      const lineHeight = await name.evaluate((el) =>
        parseFloat(getComputedStyle(el).lineHeight),
      );
      expect(box!.height).toBeLessThanOrEqual(lineHeight * 1.5);
      const overflowing = await page
        .getByTestId(`api-token-row-${created.id}`)
        .evaluate((row) =>
          Array.from(row.querySelectorAll('td')).flatMap((td) => {
            const cell = td.getBoundingClientRect();
            if (cell.width === 0) return [];
            return Array.from(td.querySelectorAll('*'))
              .filter((el) => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return false;
                return (
                  r.left < cell.left - 1 ||
                  r.right > cell.right + 1 ||
                  el.scrollWidth > el.clientWidth + 1
                );
              })
              .map((el) => el.textContent?.slice(0, 40) ?? el.tagName);
          }),
        );
      expect(overflowing).toEqual([]);
    }
    await page.setViewportSize(VIEWPORTS[0][1]);

    const section = page.getByTestId('org-settings-api-access');
    const secretPart = created.token.split('_').slice(2).join('_');
    await expect(section).not.toContainText(secretPart);
    await shoot(
      page,
      'api-access-list',
      page.getByTestId(`api-token-row-${created.id}`),
    );
  });
});
