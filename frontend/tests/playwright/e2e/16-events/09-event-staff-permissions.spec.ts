import {
  expect,
  getEventsTestData,
  loginEventLeagueStaff,
  postWithCsrf,
  resetEventsData,
  test,
} from '../../fixtures';

const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
const API_URL = `https://${DOCKER_HOST}/api`;

test.describe('Event staff permissions — league staff @cicd', () => {
  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('league staff sees admin actions on Events Test League event', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginEventLeagueStaff(context);

    await page.goto(`/events/${eventInfo.pk}`);

    // Desktop admin row visible (state SIGNUPS_OPEN by default after resetEventsData)
    await expect(page.getByTestId('event-edit-btn')).toBeVisible();
    await expect(page.getByTestId('event-start-rollcall-btn')).toBeVisible();

    // Admin-add button on the Signups tab
    await page.getByRole('tab', { name: /signups/i }).click();
    await expect(page.getByTestId('admin-add-signup-btn')).toBeVisible();
  });

  test('league staff can reopen signups from roll_call', async ({ page, context }) => {
    const eventInfo = await getEventsTestData(context);
    await loginEventLeagueStaff(context);

    // Force the event into ROLL_CALL via the CSRF-aware helper.
    await postWithCsrf(context, `${API_URL}/events/${eventInfo.pk}/start_roll_call/`);

    await page.goto(`/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Roll Call/i);

    await page.getByTestId('event-reopen-signups-btn').click();

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${eventInfo.pk}/reopen_signups/`) &&
          r.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /^Reopen Signups$/ }).last().click(),
    ]);
    expect(response.status()).toBe(200);
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Signups Open/i);
  });
});
