/**
 * Staff void of a withdrawal (#495).
 *
 * Each test builds its own full two-seat event where A withdrew and the
 * waitlisted C took the seat, so tests never share signup state.
 */

import type { BrowserContext, Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';
import { API_URL } from '../../fixtures/base-url';
import {
  getCsrfToken,
  getEventsSeedData,
  type EventsTestData,
} from '../../fixtures/events';

interface Signup {
  id: number;
  user: number;
  status: string;
  line_rank: number | null;
}

interface OrgOverrideSettings {
  staff_override_policy: string;
  staff_override_warning_codes: string[];
}

interface FullEvent {
  eventId: number;
  a: Signup;
  b: Signup;
  c: Signup;
}

let eventInfo: EventInfo;
let users: EventsTestData['users'];
let previousSettings: OrgOverrideSettings | undefined;
const createdEventIds: number[] = [];

async function post(
  context: BrowserContext,
  path: string,
  body: Record<string, unknown> = {},
) {
  const response = await postWithCsrf(context, `${API_URL}${path}`, body);
  expect(response.ok(), `${path}: ${await response.text()}`).toBeTruthy();
  return response.json();
}

async function patchOrgSettings(
  context: BrowserContext,
  body: OrgOverrideSettings,
): Promise<OrgOverrideSettings> {
  const response = await context.request.patch(
    `${API_URL}/organizations/${eventInfo.orgPk}/settings/`,
    {
      data: body,
      headers: { 'X-CSRFToken': await getCsrfToken(context) },
    },
  );
  expect(response.ok(), `settings: ${await response.text()}`).toBeTruthy();
  return response.json();
}

async function signupsFor(
  context: BrowserContext,
  eventId: number,
): Promise<Signup[]> {
  const response = await context.request.get(
    `${API_URL}/events/signups/?event=${eventId}`,
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function signupById(
  context: BrowserContext,
  eventId: number,
  signupId: number,
): Promise<Signup> {
  const signup = (await signupsFor(context, eventId)).find(
    (s) => s.id === signupId,
  );
  expect(signup, `signup ${signupId}`).toBeDefined();
  return signup!;
}

async function signUpAs(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<Signup> {
  await loginAsUser(context, userPk);
  return post(context, `/events/${eventId}/signup/`, { intent: 'rsvp' });
}

async function buildFullEventWithWithdrawal(
  context: BrowserContext,
): Promise<FullEvent> {
  await loginEventAdmin(context);
  const name = `Void Withdrawal ${Date.now()}`;
  const event = await post(context, '/events/', {
    organization: eventInfo.orgPk,
    name,
    scheduled_at: new Date(Date.now() + 86400000).toISOString(),
    tournament_name: name,
    tournament_league: eventInfo.eventsLeaguePk,
    tournament_type: 'single_elimination',
    game_type: 1,
    auto_approve: true,
    max_players: 2,
  });
  const eventId = event.id as number;
  createdEventIds.push(eventId);
  await post(context, `/events/${eventId}/open_signups/`);

  const a = await signUpAs(context, eventId, users.player);
  const b = await signUpAs(context, eventId, users.player_2);
  const c = await signUpAs(context, eventId, users.player_4);
  expect([a.status, b.status, c.status]).toEqual([
    'approved',
    'approved',
    'waitlisted',
  ]);

  await loginAsUser(context, users.player);
  const withdrawn: Signup = await post(
    context,
    `/events/signups/${a.id}/cancel_signup/`,
  );
  expect(withdrawn.status).toBe('cancelled');

  await loginEventAdmin(context);
  expect((await signupById(context, eventId, c.id)).status).toBe('approved');
  return { eventId, a, b, c };
}

async function expectStatus(
  context: BrowserContext,
  eventId: number,
  signupId: number,
  status: string,
) {
  await expect
    .poll(async () => (await signupById(context, eventId, signupId)).status)
    .toBe(status);
}

async function confirmOverride(page: Page, reason: string) {
  const dialog = page.getByTestId('override-warning-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('override-violations')).toContainText(
    'capacity',
  );
  await dialog.getByTestId('override-reason').fill(reason);
  await dialog.getByTestId('override-confirm').click();
  await expect(dialog).not.toBeVisible();
}

test.describe('Void withdrawal (@cicd)', () => {
  test.setTimeout(90_000);

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      eventInfo = await getEventsTestData(context);
      users = (await getEventsSeedData(context)).users;
      await loginEventAdmin(context);
      const response = await context.request.get(
        `${API_URL}/organizations/${eventInfo.orgPk}/settings/`,
      );
      expect(response.ok()).toBeTruthy();
      const current: OrgOverrideSettings = await response.json();
      previousSettings = {
        staff_override_policy: current.staff_override_policy,
        staff_override_warning_codes: current.staff_override_warning_codes,
      };
      await patchOrgSettings(context, {
        staff_override_policy: 'confirm',
        staff_override_warning_codes: ['over_capacity'],
      });
    } finally {
      await context.close();
    }
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginEventAdmin(context);
      const csrf = await getCsrfToken(context);
      for (const id of createdEventIds) {
        const response = await context.request.delete(
          `${API_URL}/events/${id}/`,
          { headers: { 'X-CSRFToken': csrf } },
        );
        expect(response.status(), `Delete event ${id}`).toBe(204);
      }
      if (previousSettings) await patchOrgSettings(context, previousSettings);
    } finally {
      await context.close();
    }
  });

  test('void from the Removed tab asks for override and restores the original place', async ({
    context,
    page,
  }) => {
    const { eventId, a, c } = await buildFullEventWithWithdrawal(context);
    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-removed').click();
    await page
      .getByTestId(`event-signup-row-${a.id}`)
      .getByTestId('event-void-withdrawal-btn')
      .click();
    await confirmOverride(page, 'withdrew by mistake');

    await expectStatus(context, eventId, a.id, 'approved');
    const restored = await signupById(context, eventId, a.id);
    const promoted = await signupById(context, eventId, c.id);
    expect(promoted.status).toBe('approved');
    expect(restored.line_rank!).toBeLessThan(promoted.line_rank!);

    await page.getByTestId('event-tab-signups').click();
    const panel = page.getByRole('tabpanel');
    const rowA = panel.getByTestId(`event-signup-row-${a.id}`);
    const rowC = panel.getByTestId(`event-signup-row-${c.id}`);
    await expect(rowA).toBeVisible();
    await expect(rowC).toBeVisible();
    const order = await panel
      .locator('[data-testid^="event-signup-row-"]')
      .evaluateAll((rows) => rows.map((r) => r.getAttribute('data-testid')));
    expect(order.indexOf(`event-signup-row-${a.id}`)).toBeLessThan(
      order.indexOf(`event-signup-row-${c.id}`),
    );
  });

  test('Restore with history on a full event goes to the back of the waitlist without seating over capacity', async ({
    context,
    page,
  }) => {
    const { eventId, a } = await buildFullEventWithWithdrawal(context);
    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-removed').click();
    const restored = page.waitForResponse(
      (r) =>
        r.url().includes(`/events/signups/${a.id}/reinstate/`) &&
        r.request().method() === 'POST',
    );
    await page
      .getByTestId(`event-signup-row-${a.id}`)
      .getByTestId('event-restore-btn')
      .click();
    expect((await restored).status()).toBe(200);
    await expect(page.getByTestId('override-warning-dialog')).toHaveCount(0);

    await expectStatus(context, eventId, a.id, 'waitlisted');
    await page.getByTestId('event-tab-waitlist').click();
    await expect(
      page.getByRole('tabpanel').getByTestId(`event-signup-row-${a.id}`),
    ).toBeVisible();
  });

  test('roll call Void asks for override and moves the row out of the removed group', async ({
    context,
    page,
  }) => {
    const { eventId, a } = await buildFullEventWithWithdrawal(context);
    await post(context, `/events/${eventId}/start_roll_call/`);
    await visitAndWaitForHydration(page, `/rollcall/${eventId}`);
    const row = page.getByTestId(`rollcall-row-${a.id}`);
    await expect(row.getByTestId('rollcall-void-withdrawal-btn')).toBeVisible();
    await row.getByTestId('rollcall-void-withdrawal-btn').click();
    await confirmOverride(page, 'roll call correction');

    await expectStatus(context, eventId, a.id, 'approved');
    await expect(row.getByTestId('rollcall-void-withdrawal-btn')).toHaveCount(
      0,
    );
    await expect(row.getByTestId('rollcall-confirm-btn')).toBeVisible();
  });

  test('member cannot void their own withdrawal', async ({ context }) => {
    const { eventId, a } = await buildFullEventWithWithdrawal(context);
    await loginAsUser(context, users.player);
    const response = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${a.id}/void-withdrawal/`,
      {},
    );
    expect(response.status()).toBe(403);
    await loginEventAdmin(context);
    expect((await signupById(context, eventId, a.id)).status).toBe('cancelled');
  });
});
