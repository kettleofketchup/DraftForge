import type { BrowserContext } from '@playwright/test';
import {
  expect,
  loginEventAdmin,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import {
  STEAM_VERIFY_EVENT_NAME,
  STEAM_VERIFY_UNVERIFIED_FRIEND_ID,
  STEAM_VERIFY_UNVERIFIED_PK,
  STEAM_VERIFY_VERIFIED_PK,
} from '../../fixtures/constants';
import { EVENTS_ORG_NAME, postWithCsrf } from '../../fixtures/events';

interface SignupRow {
  id: number;
  user: number;
}

async function findEventId(context: BrowserContext): Promise<number> {
  const orgs = await (
    await context.request.get(`${API_URL}/organizations/`)
  ).json();
  const org = orgs.find((o: { name: string }) => o.name === EVENTS_ORG_NAME);
  expect(org, `${EVENTS_ORG_NAME} not populated`).toBeTruthy();
  const events = await (
    await context.request.get(`${API_URL}/events/?organization=${org.pk}`)
  ).json();
  const event = events.find(
    (e: { name: string }) => e.name === STEAM_VERIFY_EVENT_NAME,
  );
  expect(event, `${STEAM_VERIFY_EVENT_NAME} not populated`).toBeTruthy();
  return event.id;
}

async function signupFor(
  context: BrowserContext,
  eventId: number,
  userPk: number,
): Promise<SignupRow> {
  const resp = await context.request.get(
    `${API_URL}/events/signups/?event=${eventId}`,
  );
  expect(resp.ok()).toBeTruthy();
  const rows: SignupRow[] = await resp.json();
  const row = rows.find((r) => r.user === userPk);
  expect(row, `no signup for user ${userPk}`).toBeTruthy();
  return row as SignupRow;
}

test.describe('Events - verify a self-reported Friend ID (@cicd)', () => {
  let eventId: number;

  test.beforeEach(async ({ context }) => {
    await loginEventAdmin(context);
    eventId = await findEventId(context);
    const reset = await postWithCsrf(
      context,
      `${API_URL}/users/${STEAM_VERIFY_UNVERIFIED_PK}/steam-verification/`,
      { verified: false, steam_account_id: STEAM_VERIFY_UNVERIFIED_FRIEND_ID },
    );
    expect(reset.ok()).toBeTruthy();
  });

  test('event admin verifies an unverified Friend ID from the approval dialog', async ({
    context,
    page,
  }) => {
    const signup = await signupFor(
      context,
      eventId,
      STEAM_VERIFY_UNVERIFIED_PK,
    );

    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId(`event-signup-row-${signup.id}`)).toBeVisible(
      { timeout: 10000 },
    );
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    await expect(
      dialog.getByTestId('steam-verification-unverified'),
    ).toBeVisible();

    await dialog.getByTestId('steam-verify-button').click();

    const verified = dialog.getByTestId('steam-verification-verified');
    await expect(verified).toBeVisible({ timeout: 10000 });
    await expect(verified).toHaveAttribute(
      'title',
      new RegExp(`Verified by ${EVENTS_ORG_NAME}`),
    );
    await expect(dialog.getByTestId('steam-verify-button')).toHaveCount(0);

    const after = await context.request.get(
      `${API_URL}/users/${STEAM_VERIFY_UNVERIFIED_PK}/steam-verification/`,
    );
    expect(after.ok()).toBeTruthy();
    const body = await after.json();
    expect(body.steam_account_verified).toBe(true);
    expect(body.steam_account_verified_org_name).toBe(EVENTS_ORG_NAME);
  });

  test('a populated verified Friend ID shows as verified by the org', async ({
    context,
    page,
  }) => {
    const signup = await signupFor(context, eventId, STEAM_VERIFY_VERIFIED_PK);

    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-signups').click();
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    const verified = dialog.getByTestId('steam-verification-verified');
    await expect(verified).toBeVisible();
    await expect(verified).toHaveAttribute(
      'title',
      new RegExp(`Verified by ${EVENTS_ORG_NAME}`),
    );
  });
});
