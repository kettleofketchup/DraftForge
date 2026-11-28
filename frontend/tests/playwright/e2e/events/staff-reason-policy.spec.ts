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
import { getCsrfToken, getEventsSeedData } from '../../fixtures/events';
import {
  closeAddUserModal,
  searchUser,
  waitForAddUserModal,
} from '../../helpers/add-user';

interface Signup {
  id: number;
  user: number;
  status: string;
}

type Policy = 'placements' | 'all_staff_changes';
let eventInfo: EventInfo;
let playerPk: number;
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

async function createEvent(context: BrowserContext, policy: Policy) {
  await loginEventAdmin(context);
  const name = `Staff Reasons ${policy} ${Date.now()}`;
  const event = await post(context, '/events/', {
    organization: eventInfo.orgPk,
    name,
    scheduled_at: new Date(Date.now() + 86400000).toISOString(),
    tournament_name: name,
    tournament_league: eventInfo.eventsLeaguePk,
    tournament_type: 'single_elimination',
    game_type: 1,
    staff_reason_policy: policy,
    auto_approve: false,
    max_players: 2,
  });
  createdEventIds.push(event.id);
  expect(event.staff_reason_policy).toBe(policy);
  await post(context, `/events/${event.id}/open_signups/`);
  return event.id as number;
}

async function signupFor(
  context: BrowserContext,
  eventId: number,
  status: 'pending' | 'approved' | 'waitlisted',
): Promise<Signup> {
  await loginAsUser(context, playerPk);
  const signup: Signup = await post(context, `/events/${eventId}/signup/`, {
    intent: 'rsvp',
  });
  await loginEventAdmin(context);
  if (status === 'pending') {
    expect(['rsvp', 'pending_approval']).toContain(signup.status);
    return signup;
  }
  const approved: Signup = await post(
    context,
    `/events/signups/${signup.id}/approve/`,
    { mmr: 3000, reason: 'E2E setup approval' },
  );
  expect(approved.status).toBe('approved');
  if (status === 'approved') return approved;
  const waitlisted: Signup = await post(
    context,
    `/events/signups/${signup.id}/demote/`,
    { reason: 'E2E setup waitlist' },
  );
  expect(waitlisted.status).toBe('waitlisted');
  return waitlisted;
}

async function openSignups(page: Page, eventId: number) {
  await visitAndWaitForHydration(page, `/events/${eventId}`);
  await page.getByTestId('event-tab-signups').click();
}

async function expectStatus(
  context: BrowserContext,
  eventId: number,
  signupId: number,
  status: string,
) {
  await expect
    .poll(async () => {
      const response = await context.request.get(
        `${API_URL}/events/signups/?event=${eventId}`,
      );
      expect(response.ok()).toBeTruthy();
      const signups: Signup[] = await response.json();
      return signups.find((s) => s.id === signupId)?.status;
    })
    .toBe(status);
}

test.describe('Staff reason policy (@cicd)', () => {
  test.setTimeout(60_000);

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      eventInfo = await getEventsTestData(context);
      playerPk = (await getEventsSeedData(context)).users.player;
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
          {
            headers: { 'X-CSRFToken': csrf },
          },
        );
        expect(response.status(), `Delete event ${id}`).toBe(204);
      }
    } finally {
      await context.close();
    }
  });

  test('placements: demoting an approved row records its reason in History', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'placements');
    const signup = await signupFor(context, eventId, 'approved');
    await openSignups(page, eventId);
    await page.getByTestId(`waitlist-signup-${signup.id}`).click();
    const dialog = page.getByTestId('staff-reason-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId('staff-reason-confirm')).toBeDisabled();
    await dialog.getByTestId('staff-reason-input').fill('moved for balance');
    await dialog.getByTestId('staff-reason-confirm').click();
    await expect(dialog).not.toBeVisible();
    await expectStatus(context, eventId, signup.id, 'waitlisted');
    await page.getByTestId('event-tab-history').click();
    await expect(
      page
        .getByTestId('signup-history-reason')
        .filter({ hasText: 'moved for balance' }),
    ).toBeVisible();
  });

  test('placements: waitlist approval recap requires a reason', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'placements');
    const signup = await signupFor(context, eventId, 'waitlisted');
    await openSignups(page, eventId);
    await page.getByTestId('event-tab-waitlist').click();
    await page.getByTestId(`approve-signup-${signup.id}`).click();
    await page.getByTestId('mmr-input').fill('3000');
    await page.getByTestId('mmr-modal-approve').click();
    await expect(page.getByTestId('mmr-confirm-approve')).toBeDisabled();
    await page.getByTestId('staff-reason-input').fill('   ');
    await expect(page.getByTestId('mmr-confirm-approve')).toBeDisabled();
    await page.getByTestId('staff-reason-input').fill('seat available');
    await page.getByTestId('mmr-confirm-approve').click();
    await expect(page.getByTestId('mmr-confirm-approve')).not.toBeVisible();
    await expectStatus(context, eventId, signup.id, 'approved');
  });

  test('placements: rejecting a pending row needs no reason dialog', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'placements');
    const signup = await signupFor(context, eventId, 'pending');
    await openSignups(page, eventId);
    await page.getByTestId(`approve-signup-${signup.id}`).click();
    await page.getByTestId('mmr-modal-reject').click();
    await expect(page.getByTestId('mmr-modal-reject')).not.toBeVisible();
    await expect(page.getByTestId('staff-reason-dialog')).toHaveCount(0);
    await expectStatus(context, eventId, signup.id, 'rejected');
  });

  test('placements: adding a site user prompts for a reason', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'placements');
    await openSignups(page, eventId);
    await page.getByTestId('admin-add-signup-btn').click();
    await waitForAddUserModal(page);
    await searchUser(page, 'event_player_1');
    await page.getByTestId('add-user-btn-event_player_1').click();
    const dialog = page.getByTestId('staff-reason-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId('staff-reason-confirm')).toBeDisabled();
    await dialog
      .getByTestId('staff-reason-input')
      .fill('late registration approved');
    const added = page.waitForResponse(
      (r) =>
        r.url().includes(`/events/${eventId}/admin-signup/`) &&
        r.request().method() === 'POST',
    );
    await dialog.getByTestId('staff-reason-confirm').click();
    expect((await added).status()).toBe(201);
    await expect(dialog).not.toBeVisible();
    await closeAddUserModal(page);
    const response = await context.request.get(
      `${API_URL}/events/signups/?event=${eventId}`,
    );
    expect(response.ok()).toBeTruthy();
    const signups: Signup[] = await response.json();
    const signup = signups.find((s) => s.user === playerPk);
    expect(signup).toBeDefined();
    await expect(
      page.getByTestId(`event-signup-row-${signup!.id}`),
    ).toBeVisible();
  });

  test('all staff changes: rejecting from the MMR modal requires a reason', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'all_staff_changes');
    const signup = await signupFor(context, eventId, 'pending');
    await openSignups(page, eventId);
    await page.getByTestId(`approve-signup-${signup.id}`).click();
    await page.getByTestId('mmr-modal-reject').click();
    const dialog = page.getByTestId('staff-reason-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId('staff-reason-confirm')).toBeDisabled();
    await dialog
      .getByTestId('staff-reason-input')
      .fill('not eligible this week');
    await dialog.getByTestId('staff-reason-confirm').click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByTestId('mmr-modal-reject')).not.toBeVisible();
    await expectStatus(context, eventId, signup.id, 'rejected');
  });

  test('all staff changes: keyboard roll call accepts 1, reason, Enter', async ({
    context,
    page,
  }) => {
    const eventId = await createEvent(context, 'all_staff_changes');
    const signup = await signupFor(context, eventId, 'approved');
    await post(context, `/events/${eventId}/start_roll_call/`);
    await visitAndWaitForHydration(page, `/rollcall/${eventId}`);
    await expect(page.getByTestId(`rollcall-row-${signup.id}`)).toHaveAttribute(
      'data-focused',
      'true',
    );
    await page.keyboard.press('1');
    const input = page.getByTestId('staff-reason-input');
    await expect(input).toBeFocused();
    await expect(
      page.getByTestId('rollcall-confirm-dialog-confirm'),
    ).toBeDisabled();
    await page.keyboard.press('Enter');
    await expect(input).toBeVisible();
    await page.keyboard.type('here');
    await page.keyboard.press('Enter');
    await expect(input).not.toBeVisible();
    await expect(
      page.getByTestId(`rollcall-cancel-btn-${signup.id}`),
    ).toBeVisible();
    await expectStatus(context, eventId, signup.id, 'confirmed');
  });
});
