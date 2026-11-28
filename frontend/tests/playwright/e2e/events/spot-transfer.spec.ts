/**
 * Spot transfer (#496): a member or staff hands a signup's place to another
 * member, swapping when the recipient already holds one.
 *
 * Each test builds its own event, so tests never share signup state.
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

interface EventOptions {
  allowSpotTransfer?: boolean;
  staffReasonPolicy?: 'placements';
}

let eventInfo: EventInfo;
let users: EventsTestData['users'];
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

async function createEvent(
  context: BrowserContext,
  { allowSpotTransfer = true, staffReasonPolicy }: EventOptions = {},
): Promise<number> {
  await loginEventAdmin(context);
  const name = `Spot Transfer ${Date.now()}`;
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
    allow_spot_transfer: allowSpotTransfer,
    ...(staffReasonPolicy ? { staff_reason_policy: staffReasonPolicy } : {}),
  });
  const eventId = event.id as number;
  createdEventIds.push(eventId);
  expect(event.allow_spot_transfer).toBe(allowSpotTransfer);
  await post(context, `/events/${eventId}/open_signups/`);
  return eventId;
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

async function signupOf(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<Signup | undefined> {
  return (await signupsFor(context, eventId)).find((s) => s.user === userPk);
}

async function signUpAs(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<Signup> {
  await loginAsUser(context, userPk);
  return post(context, `/events/${eventId}/signup/`, { intent: 'rsvp' });
}

async function pickRecipient(page: Page, username: string, userPk: number) {
  const dialog = page.getByTestId('transfer-spot-dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByTestId('transfer-spot-search').fill(username);
  await dialog.getByTestId(`transfer-spot-option-${userPk}`).click();
  return dialog;
}

async function openMemberDialog(page: Page, eventId: number) {
  await visitAndWaitForHydration(page, `/events/${eventId}`);
  await page.getByTestId('event-transfer-spot-btn').click();
}

test.describe('Spot transfer (@cicd)', () => {
  test.setTimeout(90_000);

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      eventInfo = await getEventsTestData(context);
      users = (await getEventsSeedData(context)).users;
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
    } finally {
      await context.close();
    }
  });

  test('member gives place to a member without one', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context);
    const a = await signUpAs(context, eventId, users.player);
    const b = await signUpAs(context, eventId, users.player_2);
    expect([a.status, b.status]).toEqual(['approved', 'approved']);
    expect(a.line_rank).not.toBeNull();

    await loginAsUser(context, users.player);
    await openMemberDialog(page, eventId);
    const dialog = await pickRecipient(page, 'event_player_4', users.player_4);
    await expect(dialog.getByTestId('transfer-spot-copy')).toContainText(
      'Give your place',
    );
    await dialog.getByTestId('transfer-spot-confirm').click();
    await expect(dialog).not.toBeVisible();

    await expect
      .poll(
        async () => (await signupOf(context, eventId, users.player))?.status,
      )
      .toBe('cancelled');
    const recipient = await signupOf(context, eventId, users.player_4);
    expect(recipient?.status).toBe('approved');
    expect(recipient?.line_rank).toBe(a.line_rank);
    expect(recipient!.line_rank!).toBeLessThan(b.line_rank!);
  });

  test('member swaps with a waitlisted member', async ({ context, page }) => {
    const eventId = await createEvent(context);
    const a = await signUpAs(context, eventId, users.player);
    await signUpAs(context, eventId, users.player_2);
    const c = await signUpAs(context, eventId, users.player_4);
    expect([a.status, c.status]).toEqual(['approved', 'waitlisted']);

    await loginAsUser(context, users.player);
    await openMemberDialog(page, eventId);
    const dialog = await pickRecipient(page, 'event_player_4', users.player_4);
    await expect(dialog.getByTestId('transfer-spot-copy')).toContainText(
      'Swap places with',
    );
    await expect(dialog.getByTestId('transfer-spot-confirm')).toHaveText(
      'Swap places',
    );
    await dialog.getByTestId('transfer-spot-confirm').click();
    await expect(dialog).not.toBeVisible();

    await expect
      .poll(
        async () => (await signupOf(context, eventId, users.player))?.status,
      )
      .toBe('waitlisted');
    const swappedA = await signupOf(context, eventId, users.player);
    const swappedC = await signupOf(context, eventId, users.player_4);
    expect(swappedC?.status).toBe('approved');
    expect(swappedC?.line_rank).toBe(a.line_rank);
    expect(swappedA?.line_rank).toBe(c.line_rank);
  });

  test('ineligible recipient shows the named requirement', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context);
    const a = await signUpAs(context, eventId, users.player);
    expect(a.status).toBe('approved');

    await loginEventAdmin(context);
    const response = await context.request.patch(
      `${API_URL}/events/${eventId}/`,
      {
        data: { min_mmr: 1000 },
        headers: { 'X-CSRFToken': await getCsrfToken(context) },
      },
    );
    expect(response.ok(), await response.text()).toBeTruthy();

    await loginAsUser(context, users.player);
    await openMemberDialog(page, eventId);
    const dialog = await pickRecipient(
      page,
      'event_player_no_profile',
      users.no_profile,
    );
    const refused = page.waitForResponse(
      (r) =>
        r.url().includes(`/events/signups/${a.id}/transfer/`) &&
        r.request().method() === 'POST',
    );
    await dialog.getByTestId('transfer-spot-confirm').click();
    expect((await refused).status()).toBe(400);
    await expect(dialog.getByTestId('transfer-spot-reasons')).toContainText(
      'Rank not declared',
    );
    await expect(dialog).toBeVisible();

    expect((await signupOf(context, eventId, users.player))?.status).toBe(
      'approved',
    );
    expect(await signupOf(context, eventId, users.no_profile)).toBeUndefined();
  });

  test('staff transfer under PLACEMENTS prompts for a reason', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, {
      staffReasonPolicy: 'placements',
    });
    const a = await signUpAs(context, eventId, users.player);
    expect(a.status).toBe('approved');

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-signups').click();
    await page
      .getByTestId(`event-signup-row-${a.id}`)
      .getByTestId('signup-transfer-btn')
      .click();
    const dialog = await pickRecipient(page, 'event_player_4', users.player_4);
    await dialog.getByTestId('transfer-spot-confirm').click();

    const reason = page.getByTestId('staff-reason-dialog');
    await expect(reason).toBeVisible();
    await expect(reason.getByTestId('staff-reason-confirm')).toBeDisabled();
    await reason.getByTestId('staff-reason-input').fill('swapped by request');
    const sent = page.waitForResponse(
      (r) =>
        r.url().includes(`/events/signups/${a.id}/transfer/`) &&
        r.request().method() === 'POST',
    );
    await reason.getByTestId('staff-reason-confirm').click();
    expect((await sent).status()).toBe(200);
    await expect(reason).not.toBeVisible();
    await expect(dialog).not.toBeVisible();

    await expect
      .poll(
        async () => (await signupOf(context, eventId, users.player))?.status,
      )
      .toBe('cancelled');
    const recipient = await signupOf(context, eventId, users.player_4);
    expect(recipient?.status).toBe('approved');
    expect(recipient?.line_rank).toBe(a.line_rank);

    await page.getByTestId('event-tab-history').click();
    await expect(
      page
        .getByTestId('signup-history-reason')
        .filter({ hasText: 'swapped by request' })
        .first(),
    ).toBeVisible();
  });

  test('setting off hides the button and API returns 400 transfer_disabled', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, { allowSpotTransfer: false });
    const a = await signUpAs(context, eventId, users.player);
    expect(a.status).toBe('approved');

    await loginAsUser(context, users.player);
    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible();
    await expect(page.getByTestId('event-transfer-spot-btn')).toHaveCount(0);

    const response = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${a.id}/transfer/`,
      { recipient_user_id: users.player_4 },
    );
    expect(response.status()).toBe(400);
    expect((await response.json()).code).toBe('transfer_disabled');
    expect((await signupOf(context, eventId, users.player))?.status).toBe(
      'approved',
    );
    expect(await signupOf(context, eventId, users.player_4)).toBeUndefined();
  });
});
