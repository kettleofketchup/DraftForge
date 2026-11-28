import type { BrowserContext, Page } from '@playwright/test';
import { expect, loginAsUser, test } from '../../fixtures/auth';
import { API_URL, BASE_URL } from '../../fixtures/base-url';
import { postWithCsrf } from '../../fixtures/events';

const EVENT_NAME = 'Signup Delivery Uncertain Event';

async function loginFeatureUser(
  context: BrowserContext,
  role: 'staff' | 'member',
) {
  const response = await context.request.get(`${API_URL}/users/`);
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  const users = Array.isArray(data) ? data : data.results;
  const user = users.find(
    (entry: { username: string }) =>
      entry.username === `signup_delivery_${role}`,
  );
  expect(user, 'Run the signup delivery populate fixture').toBeTruthy();
  await loginAsUser(context, user.pk);
}

async function fixtureEvent(context: BrowserContext): Promise<number> {
  const response = await context.request.get(
    `${API_URL}/events/?search=${encodeURIComponent(EVENT_NAME)}`,
  );
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  const events = Array.isArray(data) ? data : data.results;
  const event = events.find(
    (entry: { name: string }) => entry.name === EVENT_NAME,
  );
  expect(event, 'Run the signup delivery populate fixture').toBeTruthy();
  return event.id ?? event.pk;
}

async function openSchedule(page: Page, eventId: number) {
  const schedule = page.waitForResponse(
    (response) =>
      response.url() === `${API_URL}/events/${eventId}/task-schedule/` &&
      response.request().method() === 'GET',
  );
  await page.goto(`${BASE_URL}/events/${eventId}`);
  await page.getByTestId('event-tab-discord').click();
  const response = await schedule;
  expect(response.ok()).toBeTruthy();
  const entries = await response.json();
  const signup = entries.find(
    (entry: { task: string }) => entry.task === 'signup_post',
  );
  expect(['ready', 'pending']).toContain(signup.status);
  expect(signup.can_fire).toBe(true);
  expect(signup.last_fired_at).toBeNull();
  await expect(
    page.getByTestId('task-schedule-entry-signup_post'),
  ).toContainText(signup.status === 'ready' ? 'Ready' : 'Pending');
}

test.describe('Signup repost queue safety', () => {
  for (const status of [200, 409]) {
    test(`uncertain first delivery requires confirmation before queue response ${status}`, async ({
      context,
      page,
    }) => {
      await loginFeatureUser(context, 'staff');
      const eventId = await fixtureEvent(context);
      const queueRequests: string[] = [];
      await page.route('**/task-schedule/*/fire/', async (route) => {
        expect(route.request().method()).toBe('POST');
        queueRequests.push(route.request().url());
        await route.fulfill({
          status,
          json:
            status === 200
              ? { fired: true, event_id: eventId }
              : { error: 'A signup post attempt is already in progress' },
        });
      });
      await openSchedule(page, eventId);
      expect(queueRequests).toHaveLength(0);
      await page.getByTestId('fire-task-signup_post').click();
      await expect(page.getByRole('alertdialog')).toContainText(
        'An earlier post may already exist',
      );
      expect(queueRequests).toHaveLength(0);
      await page.getByTestId('task-fire-cancel').click();
      await expect(page.getByRole('alertdialog')).toHaveCount(0);
      expect(queueRequests).toHaveLength(0);
      await page.getByTestId('fire-task-signup_post').click();
      await expect(page.getByTestId('task-fire-confirm')).toContainText(
        'Queue repost',
      );
      expect(queueRequests).toHaveLength(0);
      await page.getByTestId('task-fire-confirm').click();
      await expect(page.locator('[data-sonner-toast]')).toContainText(
        status === 200
          ? 'Task "signup_post" queued'
          : 'A signup post attempt is already in progress',
      );
      expect(queueRequests).toEqual([
        `${API_URL}/events/${eventId}/task-schedule/signup_post/fire/`,
      ]);
    });
  }

  test('member cannot see repost controls or queue through the API', async ({
    context,
    page,
  }) => {
    await loginFeatureUser(context, 'member');
    const eventId = await fixtureEvent(context);
    const queueRequests: string[] = [];
    await page.route('**/task-schedule/*/fire/', async (route) => {
      queueRequests.push(route.request().url());
      await route.fulfill({
        status: 409,
        json: { error: 'Unexpected browser queue request' },
      });
    });
    await page.goto(`${BASE_URL}/events/${eventId}`);
    await expect(page.getByTestId('event-tab-signups')).toBeVisible();
    await expect(page.getByTestId('event-tab-discord')).toHaveCount(0);
    await expect(page.getByTestId('fire-task-signup_post')).toHaveCount(0);
    expect(queueRequests).toHaveLength(0);
    const response = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/task-schedule/signup_post/fire/`,
    );
    expect(response.status()).toBe(403);
  });
});
