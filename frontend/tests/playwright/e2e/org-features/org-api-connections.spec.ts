/**
 * Org API connections end to end: management, scoped inbound keys, MMR pull
 * and push, recovery and promotion backlog release.
 *
 * Simulated external I/O: every outbound request (pull pages, push
 * deliveries, health tests) goes to the fixture's synthetic `.test` origins
 * and is answered by the backend's test-only fake transport. The management
 * API, inbound key admission and the run/delivery step services are real;
 * the pinned TLS transport itself is covered by backend safe-HTTP tests.
 */
import type { BrowserContext, Page } from '@playwright/test';

import {
  connectionApi,
  driveOrgApiConnections,
  expect,
  loginOrgApiConnections,
  machineRequest,
  orgApiConnectionsState,
  orgFeaturesApi,
  resetOrgApiConnections,
  seedPromotionBacklog,
  test,
  visitAndWaitForHydration,
  type ConnectionRow,
  type OrgApiConnectionsTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

interface IssuedKey {
  connection: ConnectionRow;
  credential: { id: number; prefix: string; token: string };
}

const KEY_FORMAT = /^dfk_[0-9a-f]+_\S+$/;

let data: OrgApiConnectionsTestData;

function pullConfig(): Record<string, unknown> {
  return {
    path: data.fake.pull_path,
    mapping: {
      list_path: 'players',
      player_id_path: 'steam_id',
      mmr_path: 'mmr',
    },
  };
}

async function openApiAccess(page: Page, orgPk: number): Promise<void> {
  await visitAndWaitForHydration(
    page,
    `/organizations/${orgPk}?settings=api-access`,
  );
  await expect(page.getByTestId('org-settings-modal')).toBeVisible();
  await expect(page.getByTestId('org-settings-api-access')).toBeVisible();
}

async function openConnection(page: Page, id: number): Promise<void> {
  await page.getByTestId(`api-connection-manage-${id}`).first().click();
  await expect(page.getByTestId('api-connection-dialog')).toBeVisible();
  await expect(page.getByTestId('api-connection-name')).toBeVisible();
}

async function tab(page: Page, name: string): Promise<void> {
  await page.getByTestId(`api-connection-tab-${name}`).click();
}

async function create(
  context: BrowserContext,
  body: Record<string, unknown>,
): Promise<ConnectionRow> {
  return connectionApi<ConnectionRow>(
    context,
    data.orgs.main.pk,
    'POST',
    '',
    body,
  );
}

async function issueKey(
  context: BrowserContext,
  connectionId: number,
): Promise<string> {
  const issued = await connectionApi<IssuedKey>(
    context,
    data.orgs.main.pk,
    'POST',
    `${connectionId}/issue-key/`,
    {},
  );
  return issued.credential.token;
}

async function outbound(
  context: BrowserContext,
  extra: Record<string, unknown>,
): Promise<ConnectionRow> {
  return create(context, {
    name: 'Rating service',
    outbound_base_url: data.fake.origin,
    outbound_auth: 'bearer',
    outbound_credential: data.fake.good_credential,
    mmr_pull_config: pullConfig(),
    ...extra,
  });
}

function mmrSyncPath(): string {
  return `/organizations/${data.orgs.main.pk}/mmr-sync/`;
}

async function storageText(page: Page): Promise<string> {
  return page.evaluate(() =>
    JSON.stringify([{ ...localStorage }, { ...sessionStorage }]),
  );
}

/** Client-side navigation: the router handles a popstate, the page never reloads. */
async function spaNavigate(page: Page, path: string): Promise<void> {
  await page.evaluate((to) => {
    const state = (window.history.state ?? {}) as { idx?: number };
    window.history.pushState(
      { ...state, idx: (state.idx ?? 0) + 1, key: `spa-${Date.now()}` },
      '',
      to,
    );
    window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
  }, path);
}

/** Re-resolve the signed-in user in the running app, as its login check does. */
async function refreshViewer(page: Page): Promise<number | null> {
  return page.evaluate(async () => {
    const path = '/app/store/userStore.ts';
    const store = (await import(/* @vite-ignore */ path)) as {
      useUserStore: {
        getState: () => {
          getCurrentUser: () => Promise<void>;
          currentUser: { pk?: number } | null;
        };
      };
    };
    await store.useUserStore.getState().getCurrentUser();
    return store.useUserStore.getState().currentUser?.pk ?? null;
  });
}

async function markPageLoad(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __spaMarker?: boolean }).__spaMarker = true;
  });
}

async function expectSamePageLoad(page: Page): Promise<void> {
  expect(
    await page.evaluate(
      () => (window as unknown as { __spaMarker?: boolean }).__spaMarker,
    ),
  ).toBe(true);
}

async function expectNoSecret(page: Page, tail: string): Promise<void> {
  await expect(page.getByTestId('api-connection-key-secret')).toHaveCount(0);
  expect(await page.content()).not.toContain(tail);
  expect(await storageText(page)).not.toContain(tail);
}

test.describe('Org features: API connections @cicd', () => {
  test.beforeEach(async ({ request }) => {
    data = await resetOrgApiConnections(request);
  });

  test('admin creates a disabled connection, then issues a key shown once with only its grants @cicd', async ({
    page,
    context,
    request,
  }) => {
    const pk = data.orgs.main.pk;
    await loginOrgApiConnections(context, 'admin');
    await openApiAccess(page, pk);

    await page.getByTestId('api-connection-create').click();
    await expect(page.getByTestId('api-connection-dialog')).toBeVisible();
    await page.getByTestId('api-connection-name').fill('Rank bot');
    await expect(page.getByTestId('api-connection-enabled')).toHaveAttribute(
      'aria-checked',
      'false',
    );
    const created = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/organizations/${pk}/api-connections/`),
    );
    await page.getByTestId('api-connection-save').click();
    const createdResp = await created;
    expect(createdResp.status()).toBe(201);
    const row = (await createdResp.json()) as ConnectionRow;
    expect(row).toMatchObject({
      enabled: false,
      inbound_enabled: false,
      mmr_push_enabled: false,
      mmr_pull_enabled: false,
      promotion_push_enabled: false,
      operations: [],
      inbound_credentials: [],
    });

    await tab(page, 'inbound');
    await expect(page.getByTestId('api-connection-key-issue')).toBeDisabled();
    await tab(page, 'general');
    await page.getByTestId('api-connection-enabled').click();
    await tab(page, 'inbound');
    await page.getByTestId('api-connection-inbound-enabled').click();
    await page.getByTestId('api-connection-op-mmr:read').click();
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/api-connections/${row.id}/`),
    );
    await page.getByTestId('api-connection-save').click();
    expect((await saved).status()).toBe(200);

    const issued = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/api-connections/${row.id}/issue-key/`),
    );
    await page.getByTestId('api-connection-key-issue').click();
    const issuedResp = await issued;
    expect(issuedResp.status()).toBe(201);
    const token = ((await issuedResp.json()) as IssuedKey).credential.token;
    const secret = page.getByTestId('api-connection-key-secret');
    await expect(secret).toHaveText(KEY_FORMAT);
    await expect(secret).toHaveText(token);
    expect(await storageText(page)).not.toContain(token);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('api-connection-key-secret')).toHaveCount(0);

    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), token)).status(),
    ).toBe(200);
    const write = await machineRequest(request, 'POST', mmrSyncPath(), token, {
      game_type: 1,
      entries: [{ steam_id: data.players.one.steam_id, mmr: 4200 }],
    });
    expect(write.status()).toBe(403);

    await page.reload();
    await expect(page.getByTestId('org-settings-api-access')).toBeVisible();
    await expect(
      page.getByTestId(`api-connection-status-${row.id}`).first(),
    ).toHaveText('Enabled');
    expect(await page.content()).not.toContain(
      token.split('_').slice(2).join('_'),
    );
  });

  test('org staff, members and other orgs cannot manage connections @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.main.pk;
    for (const role of ['staff', 'member', 'second_admin'] as const) {
      await loginOrgApiConnections(context, role);
      const list = await context.request.get(
        `${API_URL}/organizations/${pk}/api-connections/`,
      );
      expect(list.status(), role).toBe(403);
      const seeded = await context.request.get(
        `${API_URL}/organizations/${pk}/api-connections/${data.seeded_connection}/`,
      );
      expect([403, 404], role).toContain(seeded.status());
    }
    for (const role of ['staff', 'member'] as const) {
      await loginOrgApiConnections(context, role);
      await visitAndWaitForHydration(
        page,
        `/organizations/${pk}?settings=api-access`,
      );
      await expect(page.getByTestId('org-tab-leagues')).toBeVisible();
      await expect(page.getByTestId('org-settings-api-access')).toHaveCount(0);
      await expect(page.getByTestId('api-connection-create')).toHaveCount(0);
    }
  });

  test('rotating ends the old key at once and revoking leaves outbound push on @cicd', async ({
    page,
    context,
    request,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const row = await outbound(context, {
      enabled: true,
      inbound_enabled: true,
      operations: ['mmr:read'],
      mmr_push_enabled: true,
    });
    const first = await issueKey(context, row.id);
    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), first)).status(),
    ).toBe(200);

    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, row.id);
    await tab(page, 'inbound');
    await page.getByTestId('api-connection-key-rotate').click();
    await page.getByTestId('api-connection-rotate-confirm').click();
    const secret = page.getByTestId('api-connection-key-secret');
    await expect(secret).toHaveText(KEY_FORMAT);
    const second = (await secret.textContent()) ?? '';
    expect(second).not.toBe(first);
    await page.keyboard.press('Escape');

    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), first)).status(),
    ).toBe(401);
    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), second)).status(),
    ).toBe(200);

    await page.getByTestId('api-connection-key-revoke').click();
    await page.getByTestId('api-connection-revoke-confirm').click();
    await expect(page.getByTestId('api-connection-key-revoke')).toHaveCount(0);
    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), second)).status(),
    ).toBe(401);

    const after = await connectionApi<ConnectionRow>(
      context,
      data.orgs.main.pk,
      'GET',
      `${row.id}/`,
    );
    expect(after).toMatchObject({
      enabled: true,
      mmr_push_enabled: true,
      credential_present: true,
    });
    await tab(page, 'push');
    await expect(
      page.getByTestId('api-connection-mmr-push-enabled'),
    ).toHaveAttribute('aria-checked', 'true');
  });

  test('the outbound credential is write-only and never reaches the browser @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.main.pk;
    const credential = data.fake.good_credential;
    await loginOrgApiConnections(context, 'admin');
    await openApiAccess(page, pk);
    await page.getByTestId('api-connection-create').click();
    await page.getByTestId('api-connection-name').fill('Credentialed');
    await page.getByTestId('api-connection-base-url').fill(data.fake.origin);
    await page.getByTestId('api-connection-auth').click();
    await page.getByRole('option', { name: 'Bearer token' }).click();
    await page.getByTestId('api-connection-credential-replace').click();
    await page.getByTestId('api-connection-credential').fill(credential);
    const created = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/organizations/${pk}/api-connections/`),
    );
    await page.getByTestId('api-connection-save').click();
    const resp = await created;
    expect(resp.status()).toBe(201);
    const body = await resp.text();
    expect(body).not.toContain(credential);
    expect(body).not.toContain('ciphertext');
    const row = JSON.parse(body) as ConnectionRow;
    expect(row.credential_present).toBe(true);

    await expect(
      page.getByTestId('api-connection-credential-status'),
    ).toContainText('Credential stored');
    await expect(page.getByTestId('api-connection-credential')).toHaveCount(0);
    await page.getByTestId('api-connection-credential-replace').click();
    await expect(page.getByTestId('api-connection-credential')).toHaveValue('');
    await page.getByTestId('api-connection-credential-keep').click();

    const read = await context.request.get(
      `${API_URL}/organizations/${pk}/api-connections/${row.id}/`,
    );
    expect(await read.text()).not.toContain(credential);
    expect(await page.content()).not.toContain(credential);
    expect(await storageText(page)).not.toContain(credential);
  });

  test('a saved disabled connection tests its pull without writing anything @cicd', async ({
    page,
    context,
    request,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const row = await outbound(context, {});
    expect(row.enabled).toBe(false);

    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, row.id);
    await tab(page, 'pull');
    await expect(page.getByTestId('api-connection-pull-now')).toBeDisabled();
    await page.getByTestId('api-connection-pull-test').click();
    await expect(page.getByTestId('api-connection-run-detail')).toBeVisible();

    await driveOrgApiConnections(request);
    await expect(page.getByTestId('api-connection-run-live')).toHaveText(
      'Run succeeded',
      { timeout: 15_000 },
    );
    const state = await orgApiConnectionsState(request);
    expect(state.mmrs[String(data.players.one.pk)]).toBe(data.players.one.mmr);
    expect(state.mmrs[String(data.players.two.pk)]).toBeUndefined();
    expect(state.deliveries).toEqual([]);
    expect(state.calls.map((c) => [c.method, c.path, c.status])).toEqual([
      ['GET', data.fake.pull_path, 200],
    ]);
  });

  test('a pull maps rows, reports unmatched players and a revision conflict @cicd', async ({
    page,
    context,
    request,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const row = await outbound(context, {
      enabled: true,
      mmr_pull_enabled: true,
      overwrite_policy: 'replace',
    });
    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, row.id);
    await tab(page, 'pull');
    await page.getByTestId('api-connection-pull-now').click();
    await expect(page.getByTestId('api-connection-run-detail')).toBeVisible();

    // The edit lands between staging and commit, so player one conflicts.
    await driveOrgApiConnections(request, {
      user_pk: data.players.one.pk,
      mmr: 3333,
    });
    await expect(page.getByTestId('api-connection-run-live')).toHaveText(
      'Run succeeded',
      { timeout: 15_000 },
    );
    const detail = page.getByTestId('api-connection-run-detail');
    const counters = detail.getByTestId('api-connection-run-counters');
    await expect(counters).toContainText('1 updated');
    await expect(counters).toContainText('1 unmatched');
    await expect(counters).toContainText('1 conflicts');
    await expect(detail.getByTestId('api-connection-run-issues')).toContainText(
      'player 839999',
    );

    const state = await orgApiConnectionsState(request);
    expect(state.mmrs[String(data.players.one.pk)]).toBe(3333);
    expect(state.mmrs[String(data.players.two.pk)]).toBe(2500);
    expect(Object.keys(state.mmrs).sort()).toEqual(
      [String(data.players.one.pk), String(data.players.two.pk)].sort(),
    );
  });

  test('a pull schedule persists across reloads @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const row = await outbound(context, {
      enabled: true,
      mmr_pull_enabled: true,
    });
    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, row.id);
    await tab(page, 'pull');
    await page.getByTestId('api-connection-schedule').click();
    await page.getByRole('option', { name: 'Every N minutes' }).click();
    await page.getByTestId('api-connection-interval').fill('90');
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/api-connections/${row.id}/`),
    );
    await page.getByTestId('api-connection-save').click();
    expect((await saved).status()).toBe(200);

    const after = await connectionApi<ConnectionRow>(
      context,
      data.orgs.main.pk,
      'GET',
      `${row.id}/`,
    );
    expect(after.interval_minutes).toBe(90);
    const due = Date.parse(after.next_due_at ?? '');
    expect(due - Date.now()).toBeGreaterThan(85 * 60_000);
    expect(due - Date.now()).toBeLessThan(91 * 60_000);

    await page.reload();
    await openConnection(page, row.id);
    await tab(page, 'pull');
    await expect(page.getByTestId('api-connection-interval')).toHaveValue('90');
  });

  test('promotion-only keys reach promotion routes but not MMR, and legacy tokens keep MMR read and write @cicd', async ({
    context,
    request,
  }) => {
    const pk = data.orgs.main.pk;
    const receipts = `/organizations/${pk}/integration/v1/contact-receipts/`;
    await loginOrgApiConnections(context, 'admin');
    const promotion = await create(context, {
      name: 'Promotion only',
      enabled: true,
      inbound_enabled: true,
      operations: ['promotion:read', 'promotion:write'],
    });
    const key = await issueKey(context, promotion.id);
    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), key)).status(),
    ).toBe(403);
    // Admitted by scope, then refused for the missing event/body.
    expect((await machineRequest(request, 'GET', receipts, key)).status()).toBe(
      400,
    );
    expect(
      (await machineRequest(request, 'POST', receipts, key, {})).status(),
    ).toBe(400);

    const { token } = await orgFeaturesApi<{ token: string }>(
      context,
      'POST',
      `/organizations/${pk}/api-tokens/`,
      { name: 'Legacy rank bot' },
    );
    expect(
      (await machineRequest(request, 'GET', mmrSyncPath(), token)).status(),
    ).toBe(200);
    expect(
      (await machineRequest(request, 'GET', receipts, token)).status(),
    ).toBe(403);
    const rows = await connectionApi<ConnectionRow[]>(context, pk, 'GET', '');
    const mapped = rows.find((r) => r.name === 'Legacy rank bot');
    expect(mapped?.operations.sort()).toEqual(['mmr:read', 'mmr:write']);
  });

  test('a rejected credential pauses deliveries until the admin repairs it and resumes @cicd', async ({
    page,
    context,
    request,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const inbound = await create(context, {
      name: 'Inbound writer',
      enabled: true,
      inbound_enabled: true,
      operations: ['mmr:write'],
    });
    const key = await issueKey(context, inbound.id);
    const push = await outbound(context, {
      enabled: true,
      mmr_push_enabled: true,
      outbound_credential: data.fake.bad_credential,
    });
    const write = await machineRequest(request, 'POST', mmrSyncPath(), key, {
      game_type: 1,
      entries: [{ steam_id: data.players.two.steam_id, mmr: 2100 }],
    });
    expect(write.status()).toBe(200);
    await driveOrgApiConnections(request);
    let state = await orgApiConnectionsState(request);
    // The writer's own connection never gets its change echoed back.
    expect(state.deliveries).toEqual([
      expect.objectContaining({
        connection_id: push.id,
        state: 'paused',
        last_reason: 'auth_failed',
      }),
    ]);

    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, push.id);
    await tab(page, 'recovery');
    await expect(
      page.getByTestId('api-connection-delivery-count-paused'),
    ).toHaveText('1');
    await expect(
      page.getByTestId('api-connection-delivery-reasons'),
    ).toContainText('1 paused');
    await tab(page, 'general');
    await page.getByTestId('api-connection-credential-replace').click();
    await page
      .getByTestId('api-connection-credential')
      .fill(data.fake.good_credential);
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/api-connections/${push.id}/`),
    );
    await page.getByTestId('api-connection-save').click();
    expect((await saved).status()).toBe(200);

    await tab(page, 'recovery');
    const resumed = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/api-connections/${push.id}/deliveries/resume/`),
    );
    await page.getByTestId('api-connection-deliveries-resume').click();
    const resumedResp = await resumed;
    expect(resumedResp.status()).toBe(200);
    expect(await resumedResp.json()).toEqual({ resumed: 1 });

    await driveOrgApiConnections(request);
    state = await orgApiConnectionsState(request);
    expect(state.deliveries.map((d) => d.state)).toEqual(['applied']);
    const posts = state.calls.filter((c) => c.method === 'POST');
    expect(posts.map((c) => [c.status, c.mmrs])).toEqual([
      [401, [2100]],
      [200, [2100]],
    ]);
  });

  test('a destination origin change needs a confirmed resync to deliver @cicd', async ({
    page,
    context,
    request,
  }) => {
    await loginOrgApiConnections(context, 'admin');
    const inbound = await create(context, {
      name: 'Inbound writer',
      enabled: true,
      inbound_enabled: true,
      operations: ['mmr:write'],
    });
    const key = await issueKey(context, inbound.id);
    const push = await outbound(context, {
      enabled: true,
      mmr_push_enabled: true,
    });
    await machineRequest(request, 'POST', mmrSyncPath(), key, {
      game_type: 1,
      entries: [{ steam_id: data.players.two.steam_id, mmr: 2200 }],
    });

    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, push.id);
    await page
      .getByTestId('api-connection-base-url')
      .fill(data.fake.moved_origin);
    await page.getByTestId('api-connection-credential-replace').click();
    await page
      .getByTestId('api-connection-credential')
      .fill(data.fake.good_credential);
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/api-connections/${push.id}/`),
    );
    await page.getByTestId('api-connection-save').click();
    expect((await saved).status()).toBe(200);

    await driveOrgApiConnections(request);
    let state = await orgApiConnectionsState(request);
    expect(state.deliveries.map((d) => [d.state, d.last_reason])).toEqual([
      ['paused', 'origin_changed'],
    ]);
    expect(state.calls).toEqual([]);

    await tab(page, 'recovery');
    await expect(
      page.getByTestId('api-connection-origin-resync'),
    ).toBeVisible();
    await page.getByTestId('api-connection-deliveries-resync').click();
    const resynced = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/api-connections/${push.id}/deliveries/resync/`),
    );
    await page.getByTestId('api-connection-resync-confirm').click();
    expect((await resynced).status()).toBe(200);

    await driveOrgApiConnections(request);
    state = await orgApiConnectionsState(request);
    const applied = state.deliveries.filter((d) => d.state === 'applied');
    expect(applied.length).toBeGreaterThan(0);
    for (const delivery of applied) {
      expect(delivery.destination_origin).toContain('ratings-moved');
    }
    expect(
      state.deliveries.filter((d) => d.last_reason === 'origin_changed'),
    ).toEqual([]);
    expect(new Set(state.calls.map((c) => c.host))).toEqual(
      new Set([new URL(data.fake.moved_origin).hostname]),
    );
  });

  test('a held promotion backlog is released only after confirming its count @cicd', async ({
    page,
    context,
    request,
  }) => {
    const { connection_id: id } = await seedPromotionBacklog(request);
    await loginOrgApiConnections(context, 'admin');
    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, id);
    await tab(page, 'recovery');
    await expect(
      page.getByTestId('api-connection-outbox-count-backlog_held'),
    ).toHaveText('3');
    await page.getByTestId('api-connection-promotion-send-backlog').click();
    await expect(page.getByRole('alertdialog')).toContainText('Send 3');
    const released = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().endsWith(`/api-connections/${id}/promotion/send-backlog/`),
    );
    await page.getByTestId('api-connection-backlog-confirm').click();
    const resp = await released;
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toEqual({ released: 3 });
    await expect(
      page.getByTestId('api-connection-outbox-count-backlog_held'),
    ).toHaveText('0');
    await expect(
      page.getByTestId('api-connection-outbox-count-pending'),
    ).toHaveText('3');
  });

  test('the editor keeps Enter from saving and asks before discarding a draft @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.main.pk;
    await loginOrgApiConnections(context, 'admin');
    await openApiAccess(page, pk);
    const writes: string[] = [];
    page.on('request', (req) => {
      if (
        req.method() !== 'GET' &&
        req.url().includes(`/organizations/${pk}`)
      ) {
        writes.push(`${req.method()} ${req.url()}`);
      }
    });

    await page.getByTestId('api-connection-create').click();
    const name = page.getByTestId('api-connection-name');
    await name.fill('Draft only');
    await name.press('Enter');
    await page.getByTestId('api-connection-base-url').fill(data.fake.origin);
    await page.getByTestId('api-connection-base-url').press('Enter');
    await expect(page.getByTestId('api-connection-dialog')).toBeVisible();

    // Submitting the host org settings form never saves the open editor.
    const hostForm = page.locator(
      'form:has([data-testid="org-settings-api-access"])',
    );
    await expect(hostForm).toHaveCount(1);
    await hostForm.evaluate((form: HTMLFormElement) => form.requestSubmit());
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('api-connection-dialog')).toBeVisible();
    await expect(name).toHaveValue('Draft only');
    expect(writes.filter((w) => w.includes('/api-connections'))).toEqual([]);
    await expect(page.getByTestId('api-connection-cancel')).toHaveText(
      'Cancel',
    );

    await page.getByTestId('api-connection-cancel').click();
    await page.getByTestId('api-connection-discard-cancel').click();
    await expect(name).toHaveValue('Draft only');
    await expect(
      page.getByTestId('api-connection-discard-confirm'),
    ).toHaveCount(0);
    await page.keyboard.press('Escape');
    await page.getByTestId('api-connection-discard-confirm').click();
    await expect(page.getByTestId('api-connection-dialog')).toHaveCount(0);
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();

    expect(writes).toEqual([]);
    expect(
      await connectionApi<ConnectionRow[]>(context, pk, 'GET', ''),
    ).toEqual([]);
  });

  test('on a phone the flow works and a shown key never survives an org or viewer switch @cicd', async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginOrgApiConnections(context, 'admin');
    const row = await create(context, { name: 'Phone key' });
    await openApiAccess(page, data.orgs.main.pk);
    await openConnection(page, row.id);

    const enabled = page.getByTestId('api-connection-enabled');
    await enabled.focus();
    await page.keyboard.press('Space');
    await expect(enabled).toHaveAttribute('aria-checked', 'true');
    await tab(page, 'inbound');
    const inbound = page.getByTestId('api-connection-inbound-enabled');
    await inbound.focus();
    await page.keyboard.press('Space');
    const read = page.getByTestId('api-connection-op-mmr:read');
    await read.focus();
    await page.keyboard.press('Space');
    await expect(read).toHaveAttribute('aria-checked', 'true');
    const save = page.getByTestId('api-connection-save');
    await save.focus();
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/api-connections/${row.id}/`),
    );
    await page.keyboard.press('Enter');
    expect((await saved).status()).toBe(200);

    await page.getByTestId('api-connection-key-issue').click();
    const secret = page.getByTestId('api-connection-key-secret');
    await expect(secret).toHaveText(KEY_FORMAT);
    const token = (await secret.textContent()) ?? '';
    const tail = token.split('_').slice(2).join('_');
    expect(await storageText(page)).not.toContain(tail);

    await markPageLoad(page);

    // Org switch inside the app: the second org shows its own seeded
    // connection, never the key.
    await spaNavigate(
      page,
      `/organizations/${data.orgs.second.pk}?settings=api-access`,
    );
    await expect(
      page
        .getByTestId(`api-connection-status-${data.seeded_connection}`)
        .first(),
    ).toHaveText('Disabled');
    await expectNoSecret(page, tail);
    await openConnection(page, data.seeded_connection);
    await tab(page, 'runs');
    await expect(page.getByTestId('api-connection-runs-table')).toContainText(
      'Succeeded',
    );
    await expectNoSecret(page, tail);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('api-connection-dialog')).toHaveCount(0);

    // Back on the first org, rotating shows a fresh key.
    await spaNavigate(
      page,
      `/organizations/${data.orgs.main.pk}?settings=api-access`,
    );
    await openConnection(page, row.id);
    await tab(page, 'inbound');
    await page.getByTestId('api-connection-key-rotate').click();
    await page.getByTestId('api-connection-rotate-confirm').click();
    await expect(secret).toHaveText(KEY_FORMAT);
    const rotated = ((await secret.textContent()) ?? '')
      .split('_')
      .slice(2)
      .join('_');
    expect(rotated).not.toBe(tail);

    // Viewer switch inside the app: another admin of the first org sees no
    // trace of either key.
    await loginOrgApiConnections(context, 'admin_two');
    expect(await refreshViewer(page)).toBe(data.users.admin_two.pk);
    await expect(
      page.getByTestId(`api-connection-status-${row.id}`).first(),
    ).toHaveText('Enabled');
    await expectNoSecret(page, rotated);
    await expectNoSecret(page, tail);
    await expectSamePageLoad(page);
  });
});
