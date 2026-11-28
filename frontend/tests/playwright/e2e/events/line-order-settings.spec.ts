/**
 * Signup line-order rules E2E (#493).
 *
 * - The two Signup Line settings persist through the edit-event dialog.
 * - On the seeded "Line Order Keep Place Event" (both rules off), a member who
 *   cancels and signs up again keeps the same signup, stamp and place.
 * - Roll call rows show when each signup joined the line.
 */

import type { BrowserContext, Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken, getEventsSeedData } from '../../fixtures/events';

const KEEP_PLACE_EVENT_NAME = 'Line Order Keep Place Event';
const ROLL_CALL_EVENT_NAME = 'Demo Roll Call Event';
const LINE_RULES = ['line_withdraw_forfeits', 'line_switch_restamps'] as const;
const SEAT_HOLDING = ['rsvp', 'pending_approval', 'approved', 'confirmed'];

interface SignupRow {
  id: number;
  user: number;
  status: string;
  signed_up_at: string | null;
  line_rank: number | null;
}

let eventInfo: EventInfo;
const createdEventIds: number[] = [];

async function eventIdByName(
  context: BrowserContext,
  name: string,
): Promise<number> {
  const resp = await context.request.get(
    `${API_URL}/events/?organization=${eventInfo.orgPk}`,
  );
  expect(resp.ok()).toBeTruthy();
  const events: { id: number; name: string }[] = await resp.json();
  const found = events.find((e) => e.name === name);
  if (!found) throw new Error(`${name} not found. Run just db::populate::all`);
  return found.id;
}

async function signups(
  context: BrowserContext,
  eventId: number,
): Promise<SignupRow[]> {
  const resp = await context.request.get(
    `${API_URL}/events/signups/?event=${eventId}`,
  );
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

async function rowFor(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<SignupRow | undefined> {
  return (await signups(context, eventId)).find((s) => s.user === userPk);
}

/** Sign the logged-in user up unless they already hold a seat. */
async function ensureSeated(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<void> {
  const row = await rowFor(context, eventId, userPk);
  if (row && SEAT_HOLDING.includes(row.status)) return;
  const resp = await postWithCsrf(
    context,
    `${API_URL}/events/${eventId}/signup/`,
    { intent: 'rsvp' },
  );
  expect(resp.ok(), `Signup failed: ${await resp.text()}`).toBeTruthy();
}

async function openApprovalTab(page: Page) {
  await page.getByTestId('event-edit-btn').click();
  const modal = page.getByTestId('edit-event-modal');
  await expect(modal).toBeVisible();
  const tab = modal.getByTestId('edit-event-tab-approval');
  await tab.click();
  await expect(tab).toHaveAttribute('data-state', 'active');
  return modal;
}

test.describe('Signup line-order rules (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginEventAdmin(context);
    const csrf = await getCsrfToken(context);
    for (const id of createdEventIds) {
      const resp = await context.request.delete(`${API_URL}/events/${id}/`, {
        headers: { 'X-CSRFToken': csrf },
      });
      expect(resp.status(), `Delete event ${id} failed`).toBe(204);
    }
    await context.close();
  });

  test('line settings persist through the edit-event dialog', async ({
    page,
    context,
  }) => {
    // Two page loads and two dialog opens; a cold dev server needs over 30s.
    test.setTimeout(60_000);
    await loginEventAdmin(context);
    const name = `Line Rules ${Date.now()}`;
    const resp = await postWithCsrf(context, `${API_URL}/events/`, {
      organization: eventInfo.orgPk,
      name,
      scheduled_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      tournament_name: name,
      tournament_league: eventInfo.eventsLeaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
    });
    expect(resp.ok(), `Create event failed: ${await resp.text()}`).toBeTruthy();
    const eventId = ((await resp.json()) as { id: number }).id;
    createdEventIds.push(eventId);

    await visitAndWaitForHydration(page, `/events/${eventId}`);
    let modal = await openApprovalTab(page);
    for (const rule of LINE_RULES) {
      const box = modal.getByTestId(`signup-line-${rule}`);
      await expect(box).toBeChecked();
      await box.click();
      await expect(box).not.toBeChecked();
    }
    await modal.getByTestId('form-dialog-submit').click();
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    await page.reload();
    modal = await openApprovalTab(page);
    for (const rule of LINE_RULES) {
      await expect(modal.getByTestId(`signup-line-${rule}`)).not.toBeChecked();
    }

    const detail = await (
      await context.request.get(`${API_URL}/events/${eventId}/`)
    ).json();
    expect(detail.line_withdraw_forfeits).toBe(false);
    expect(detail.line_switch_restamps).toBe(false);
  });

  test('re-sign-up keeps the signup and its place when withdrawing does not forfeit', async ({
    page,
    context,
  }) => {
    const { users } = await getEventsSeedData(context);
    const eventId = await eventIdByName(context, KEEP_PLACE_EVENT_NAME);
    const detail = await (
      await context.request.get(`${API_URL}/events/${eventId}/`)
    ).json();
    expect(detail.line_withdraw_forfeits).toBe(false);

    await loginEventPlayer4(context);
    await ensureSeated(context, eventId, users.player_4);
    await loginEventPlayer(context);
    await ensureSeated(context, eventId, users.player);

    const before = await rowFor(context, eventId, users.player);
    const behind = await rowFor(context, eventId, users.player_4);
    expect(before?.signed_up_at).toBeTruthy();
    expect(before!.line_rank).toBeLessThan(behind!.line_rank!);

    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-cancel-rsvp-btn').click();
    await page
      .getByRole('alertdialog')
      .getByRole('button', { name: 'Cancel RSVP' })
      .click();
    await expect(page.getByTestId('event-signup-btn')).toBeVisible({
      timeout: 10000,
    });
    await page.getByTestId('event-signup-btn').click();
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({
      timeout: 10000,
    });

    const after = await rowFor(context, eventId, users.player);
    expect(after?.id).toBe(before!.id);
    expect(after?.signed_up_at).toBe(before!.signed_up_at);
    expect(after?.line_rank).toBe(before!.line_rank);
    expect(after!.line_rank).toBeLessThan(
      (await rowFor(context, eventId, users.player_4))!.line_rank!,
    );

    await page.getByTestId('event-tab-signups').click();
    await expect(
      page.getByTestId(`signup-in-line-since-${before!.id}`),
    ).toBeVisible({ timeout: 10000 });
  });

  test('roll call rows show when each signup joined the line', async ({
    page,
    context,
  }) => {
    await loginEventAdmin(context);
    const eventId = await eventIdByName(context, ROLL_CALL_EVENT_NAME);
    const rows = (await signups(context, eventId)).filter((s) =>
      SEAT_HOLDING.includes(s.status),
    );
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0].signed_up_at).toBeTruthy();

    await visitAndWaitForHydration(page, `/rollcall/${eventId}`);
    await expect(
      page.getByTestId(`signup-in-line-since-${rows[0].id}`),
    ).toBeVisible({ timeout: 15000 });
  });
});
