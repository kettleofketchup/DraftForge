import type { BrowserContext, Page } from '@playwright/test';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';

interface RecordsData {
  org_pk: number;
  admin_pk: number;
  staff_pk: number;
  member_pk: number;
  cancel_event_pk: number;
  delete_event_pk: number;
  registered_event_pk: number;
  empty_event_pk: number;
  repeater_pk: number;
}

let data: RecordsData;

async function reset(context: BrowserContext): Promise<RecordsData> {
  const response = await context.request.post(
    `${API_URL}/tests/signup-records/reset/`,
  );
  expect(response.status()).toBe(200);
  return response.json();
}

async function event(context: BrowserContext, id: number) {
  const response = await context.request.get(`${API_URL}/events/${id}/`);
  expect(response.status()).toBe(200);
  return response.json();
}

async function roster(context: BrowserContext, id: number) {
  const response = await context.request.get(
    `${API_URL}/events/signups/?event=${id}`,
  );
  expect(response.status()).toBe(200);
  const body = await response.json();
  return (Array.isArray(body) ? body : body.results) as {
    id: number;
    status: string;
    user: number;
  }[];
}

async function openDeletion(page: Page, id: number, mobile = false) {
  await visitAndWaitForHydration(page, `/events/${id}`);
  if (mobile) {
    await page.getByTestId('event-admin-actions-mobile').click();
    await page.getByTestId('event-mobile-delete').click();
  } else {
    await page.getByTestId('event-delete-btn').click();
  }
  await page.getByTestId('event-delete-initial-confirm').click();
  await expect(page.getByTestId('event-delete-record-warning')).toBeVisible();
}

async function openHistory(page: Page) {
  if (await page.getByTestId('event-tab-history').isVisible()) {
    await page.getByTestId('event-tab-history').click();
  } else {
    await page.getByTestId('page-nav-trigger').click();
    await page.getByTestId('page-nav-history').click();
  }
  await expect(page.getByTestId('signup-history-section')).toBeVisible();
}

test.describe('Signup records survive lifecycle actions (@cicd)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ context }) => {
    data = await reset(context);
    await loginAsUser(context, data.staff_pk);
  });

  test('staff cancellation preserves signup identities, statuses and history', async ({
    context,
    page,
  }) => {
    const before = await roster(context, data.cancel_event_pk);
    expect(before).toHaveLength(1);
    await visitAndWaitForHydration(page, `/events/${data.cancel_event_pk}`);
    await page.getByTestId('event-cancel-btn').click();
    await expect
      .poll(async () => (await event(context, data.cancel_event_pk)).state)
      .toBe('cancelled');
    expect(await roster(context, data.cancel_event_pk)).toEqual(before);
    await openHistory(page);
    await expect(
      page
        .getByTestId(/^signup-history-row-\d+$/)
        .filter({ hasText: 'Event cancelled' }),
    ).toHaveCount(1);
    const history = await context.request.get(
      `${API_URL}/events/${data.cancel_event_pk}/signup-history/`,
    );
    expect(history.status()).toBe(200);
    expect(
      (await history.json()).results.filter(
        (entry: { action: string }) => entry.action === 'event_cancelled',
      ),
    ).toHaveLength(1);
  });

  test('staff gets a warning, cannot forge confirmation, and can cancel instead', async ({
    context,
    page,
  }) => {
    await openDeletion(page, data.delete_event_pk);
    await expect(page.getByTestId('event-delete-record-count')).toHaveText('1');
    await expect(page.getByTestId('event-delete-confirm-input')).toHaveCount(0);
    await expect(page.getByTestId('event-delete-record-confirm')).toHaveCount(
      0,
    );
    const csrf = await getCsrfToken(context);
    const response = await context.request.delete(
      `${API_URL}/events/${data.delete_event_pk}/?confirm=true`,
      {
        headers: { 'X-CSRFToken': csrf },
      },
    );
    expect(response.status()).toBe(403);
    await page.getByTestId('event-delete-cancel-instead').click();
    await expect
      .poll(async () => (await event(context, data.delete_event_pk)).state)
      .toBe('cancelled');
    await expect(page).toHaveURL(new RegExp(`/events/${data.delete_event_pk}`));
  });

  test('admin explicitly types the name before confirmed deletion', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.admin_pk);
    const original = await event(context, data.delete_event_pk);
    const deletes: string[] = [];
    page.on('request', (request) => {
      if (request.method() === 'DELETE') deletes.push(request.url());
    });
    await openDeletion(page, data.delete_event_pk);
    await expect(
      page.getByTestId('event-delete-record-confirm'),
    ).toBeDisabled();
    expect(deletes).toHaveLength(1);
    expect(deletes[0]).not.toContain('confirm=');
    await page.getByTestId('event-delete-confirm-input').fill(original.name);
    await page.getByTestId('event-delete-record-confirm').click();
    await expect(page).toHaveURL(/\/events$/);
    expect(deletes).toHaveLength(2);
    expect(deletes[1]).toContain('confirm=true');
    expect(
      (
        await context.request.get(`${API_URL}/events/${data.delete_event_pk}/`)
      ).status(),
    ).toBe(404);
  });

  test('mobile admin Enter on cancellation after name matching never confirms DELETE', async ({
    context,
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAsUser(context, data.admin_pk);
    const original = await event(context, data.delete_event_pk);
    const deletes: string[] = [];
    page.on('request', (request) => {
      if (request.method() === 'DELETE') deletes.push(request.url());
    });
    await openDeletion(page, data.delete_event_pk, true);
    await page.getByTestId('event-delete-confirm-input').fill(original.name);
    const cancel = page.getByTestId('event-delete-cancel-instead');
    await cancel.focus();
    await cancel.press('Enter');
    await expect
      .poll(async () => (await event(context, data.delete_event_pk)).state)
      .toBe('cancelled');
    expect(deletes).toHaveLength(1);
    expect(deletes[0]).not.toContain('confirm=');
    await expect(page.getByTestId('event-delete-record-dialog')).toBeHidden();
    await expect(page).toHaveURL(new RegExp(`/events/${data.delete_event_pk}`));
  });

  test('series deletion keeps registered occurrences cancelled and standalone', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.admin_pk);
    const before = await roster(context, data.registered_event_pk);
    await visitAndWaitForHydration(page, `/events/${data.registered_event_pk}`);
    await page.evaluate(() => {
      (window as unknown as { __recordsNoReload: boolean }).__recordsNoReload =
        true;
    });
    await page.getByTestId('event-series-link').click();
    await page.getByTestId('delete-series-btn').click();
    await page
      .getByTestId('delete-series-confirm-input')
      .fill('Records Weekly Series');
    await page.getByTestId('delete-series-confirm').click();
    await expect(page).toHaveURL(/\/events$/);
    const retained = await event(context, data.registered_event_pk);
    expect(retained.state).toBe('cancelled');
    expect(retained.event_repeater).toBeNull();
    expect(await roster(context, data.registered_event_pk)).toEqual(before);
    expect(
      (
        await context.request.get(`${API_URL}/events/${data.empty_event_pk}/`)
      ).status(),
    ).toBe(404);
    await page.goBack();
    await page.goBack();
    await expect(page).toHaveURL(
      new RegExp(`/events/${data.registered_event_pk}`),
    );
    await expect(page.getByTestId('event-cancel-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-series-link')).toHaveCount(0);
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { __recordsNoReload?: boolean })
            .__recordsNoReload,
      ),
    ).toBe(true);
    await expect(
      page.getByRole('heading', { name: retained.name, exact: true }),
    ).toBeVisible();
  });
});
