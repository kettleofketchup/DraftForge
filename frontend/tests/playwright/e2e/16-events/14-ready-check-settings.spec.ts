/**
 * Ready check settings E2E tests (#528).
 *
 * Settings are stored only; no ready check runs yet. Uses the Events Test Org
 * and the seeded "Demo Ready Check Event" (6 approved + 1 dropped signup).
 */

import type { BrowserContext, Page, Route } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginAsUser,
  loginEventAdmin,
  patchWithCsrf,
  resetEventsData,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const DEMO_EVENT_NAME = 'Demo Ready Check Event';
const VOICE_CHANNEL = {
  id: '100000000000000528',
  name: 'Event Voice',
  type: 2,
  type_label: 'voice',
};
const VOICE_CHANNELS_URL =
  /\/api\/discord\/organizations\/\d+\/channels\/\?(?:.*&)?kind=voice/;
const READY_CHECK_KEYS = [
  'roll_call_enabled',
  'roll_call_mode',
  'auto_confirm',
  'ready_check_scope',
  'ready_check_open_minutes',
  'ready_check_escalation_minutes',
  'ready_check_close_minutes',
  'ready_check_chase_minutes',
  'ready_check_min_completion_pct',
  'ready_check_low_completion_action',
  'ready_check_notify_on_signup',
  'ready_check_drop_notice',
  'start_cull_enabled',
  'start_cull_minutes_after',
  'post_cull_fill_mode',
  'event_voice_channel_id',
  'voice_presence_confirms',
] as const;

type Defaults = Record<string, unknown> & { id: number };

let eventInfo: EventInfo;

async function getDefaults(context: BrowserContext): Promise<Defaults> {
  const resp = await context.request.get(
    `${API_URL}/events/defaults/?organization=${eventInfo.orgPk}`,
  );
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

async function stubVoiceChannels(page: Page) {
  await page.route(VOICE_CHANNELS_URL, (route: Route) =>
    route.fulfill({ json: { channels: [VOICE_CHANNEL] } }),
  );
}

async function openTab(page: Page, prefix: string, tab: string) {
  const trigger = page.getByTestId(`${prefix}-tab-${tab}`);
  await trigger.click();
  await expect(trigger).toHaveAttribute('data-state', 'active');
}

async function openCreateEvent(page: Page) {
  await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
  await page.getByTestId('org-tab-events').click();
  await page.getByTestId('create-event-btn').click();
  await expect(page.getByTestId('event-name-input')).toBeVisible();
}

async function createEventWithToggle(
  page: Page,
  name: string,
  finalToggle: boolean,
): Promise<number> {
  await openCreateEvent(page);
  await page.getByTestId('event-name-input').fill(name);
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  await page
    .getByTestId('event-scheduled-input')
    .fill(tomorrow.toISOString().slice(0, 16));

  await openTab(page, 'event-modal', 'tournament');
  await page.getByTestId('event-tournament-name-input').fill(`${name} T`);
  await page.getByTestId('event-league-select').click();
  await page
    .getByRole('option', { name: 'Events Test League', exact: true })
    .click();

  await openTab(page, 'event-modal', 'ready');
  const toggle = page.getByTestId('ready-check-toggle');
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  if (!finalToggle) {
    await toggle.click();
    await expect(toggle).not.toBeChecked();
  }

  await page.getByTestId('form-dialog-submit').click();
  await expect(
    page.getByRole('heading', { name: 'Create Event' }),
  ).not.toBeVisible({ timeout: 10000 });

  const resp = await page.request.get(
    `${API_URL}/events/?organization=${eventInfo.orgPk}`,
  );
  expect(resp.ok()).toBeTruthy();
  const events: { id: number; name: string }[] = await resp.json();
  const created = events.find((e) => e.name === name);
  expect(created).toBeTruthy();
  return created!.id;
}

async function findDemoEvent(context: BrowserContext): Promise<number> {
  const resp = await context.request.get(
    `${API_URL}/events/?organization=${eventInfo.orgPk}`,
  );
  expect(resp.ok()).toBeTruthy();
  const events: { id: number; name: string }[] = await resp.json();
  const demo = events.find((e) => e.name === DEMO_EVENT_NAME);
  if (!demo) throw new Error(`${DEMO_EVENT_NAME} not found. Repopulate.`);
  return demo.id;
}

async function getDemoSignups(context: BrowserContext, eventId: number) {
  const resp = await context.request.get(
    `${API_URL}/events/signups/?event=${eventId}`,
  );
  expect(resp.ok()).toBeTruthy();
  const signups: { id: number; user: number; status: string }[] =
    await resp.json();
  const dropped = signups.find((s) => s.status === 'dropped');
  const approved = signups.find((s) => s.status === 'approved');
  if (!dropped || !approved) throw new Error('Demo signups missing');
  return { dropped, approved };
}

test.describe.serial('Events - Ready check settings (@cicd)', () => {
  let snapshot: Partial<Defaults> = {};
  let defaultsId: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await loginEventAdmin(context);
    const defaults = await getDefaults(context);
    defaultsId = defaults.id;
    snapshot = Object.fromEntries(
      READY_CHECK_KEYS.map((k) => [k, defaults[k]]),
    );
    await context.close();
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginEventAdmin(context);
    const resp = await patchWithCsrf(
      context,
      `${API_URL}/events/defaults/${defaultsId}/`,
      snapshot,
    );
    expect(resp.ok()).toBeTruthy();
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('ready check toggle sets the preset on create', async ({ page }) => {
    const stamp = Date.now();
    const onId = await createEventWithToggle(
      page,
      `E2E Ready On ${stamp}`,
      true,
    );
    const on = await (
      await page.request.get(`${API_URL}/events/${onId}/`)
    ).json();
    expect(on.roll_call_enabled).toBe(true);
    expect(on.roll_call_mode).toBe('automatic');
    expect(on.auto_confirm).toBe(false);
    expect(on.ready_check_open_minutes).toBe(120);

    const offId = await createEventWithToggle(
      page,
      `E2E Ready Off ${stamp}`,
      false,
    );
    const off = await (
      await page.request.get(`${API_URL}/events/${offId}/`)
    ).json();
    expect(off.roll_call_enabled).toBe(false);
  });

  test('org defaults keep the reference preset and pre-fill new events', async ({
    context,
    page,
  }) => {
    await stubVoiceChannels(page);
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();
    await expect(page.getByTestId('org-events-heading')).toBeVisible();
    await page.getByTestId('org-settings-button').click();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();

    await openTab(page, 'org-settings', 'defaults-ready');
    await page.getByTestId('ready-check-toggle').click();
    await expect(page.getByTestId('ready-check-toggle')).toBeChecked();
    await expect(page.getByTestId('ready-check-auto-confirm')).toBeDisabled();

    await page.getByTestId('ready-check-settings-trigger').click();
    await page.getByTestId('ready-check-scope').click();
    await page.getByTestId('ready-check-scope-main_and_fill').click();
    await page.getByTestId('ready-check-chase-minutes').fill('20');

    await page.getByTestId('ready-check-voice-trigger').click();
    await page.getByTestId('ready-check-voice-channel').click();
    await page.getByRole('option', { name: VOICE_CHANNEL.name }).click();
    await page.getByTestId('ready-check-cull-enabled').click();
    await expect(page.getByTestId('ready-check-cull-enabled')).toBeChecked();

    await page.getByTestId('org-settings-save').click();
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0, {
      timeout: 10000,
    });

    const saved = await getDefaults(context);
    expect(saved).toMatchObject({
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
      auto_confirm: false,
      ready_check_scope: 'main_and_fill',
      ready_check_min_completion_pct: 70,
      ready_check_low_completion_action: 'non_binding',
      ready_check_chase_minutes: 20,
      start_cull_enabled: true,
      start_cull_minutes_after: 1,
      post_cull_fill_mode: 'line_order',
      event_voice_channel_id: VOICE_CHANNEL.id,
    });

    await page.reload();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await openTab(page, 'org-settings', 'defaults-ready');
    await expect(page.getByTestId('ready-check-toggle')).toBeChecked();
    await page.getByTestId('ready-check-settings-trigger').click();
    await expect(page.getByTestId('ready-check-chase-minutes')).toHaveValue(
      '20',
    );
    await expect(page.getByTestId('ready-check-scope')).toContainText(
      'Main roster and fill list',
    );
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('org-settings-modal')).not.toBeVisible();

    await page.getByTestId('create-event-btn').click();
    await expect(page.getByTestId('event-name-input')).toBeVisible();
    await openTab(page, 'event-modal', 'ready');
    await expect(page.getByTestId('ready-check-toggle')).toBeChecked();
    await page.getByTestId('ready-check-settings-trigger').click();
    await expect(page.getByTestId('ready-check-chase-minutes')).toHaveValue(
      '20',
    );
    await expect(page.getByTestId('ready-check-mode')).toContainText(
      'Automatic',
    );
    await page.getByTestId('ready-check-voice-trigger').click();
    await expect(page.getByTestId('ready-check-cull-enabled')).toBeChecked();
    await expect(page.getByTestId('ready-check-voice-channel')).toContainText(
      VOICE_CHANNEL.name,
    );
  });

  test('staff see the dropped member as removed and not counted', async ({
    context,
    page,
  }) => {
    const eventId = await findDemoEvent(context);
    const { dropped, approved } = await getDemoSignups(context, eventId);
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    await expect(page.getByTestId('event-tab-signups')).toContainText('(6)');
    await page.getByTestId('event-tab-signups').click();
    const approvedRow = page.getByTestId(`event-signup-row-${approved.id}`);
    await expect(approvedRow).toBeVisible({ timeout: 10000 });
    await expect(
      approvedRow.getByRole('button', { name: 'Remove' }),
    ).toBeVisible();

    await expect(page.getByTestId('event-tab-removed')).toContainText('(1)');
    await page.getByTestId('event-tab-removed').click();
    const droppedRow = page.getByTestId(`event-signup-row-${dropped.id}`);
    await expect(droppedRow).toBeVisible({ timeout: 10000 });
    await expect(droppedRow).toContainText('Dropped');
    await expect(
      droppedRow.getByRole('button', { name: 'Remove' }),
    ).toHaveCount(0);
    await expect(droppedRow.getByTestId('event-restore-btn')).toHaveCount(0);
  });

  test('the dropped member sees a notice instead of signup actions', async ({
    context,
    page,
  }) => {
    const eventId = await findDemoEvent(context);
    const { dropped } = await getDemoSignups(context, eventId);
    await loginAsUser(context, dropped.user);
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    const notice = page.getByTestId('event-dropped-notice');
    await expect(notice).toBeVisible({ timeout: 10000 });
    await expect(notice).toContainText('You were dropped from this event');
    await expect(page.getByTestId('event-signup-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-tentative-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-cancel-tentative-btn')).toHaveCount(0);
  });
});
