import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  loginEventPlayer,
  resetEventsData,
  setApprovedMmr,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import { postWithCsrf } from '../../fixtures/events';

let eventInfo: EventInfo;

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

test.describe('Events - approval dialog fits the viewport (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  for (const viewport of VIEWPORTS) {
    test(`approval actions stay on screen with the delta warning (${viewport.name})`, async ({
      context,
      page,
    }) => {
      const createResp = await postWithCsrf(
        context,
        `${API_URL}/events/?open_signups=true`,
        {
          organization: eventInfo.orgPk,
          name: `Approval Viewport Event ${viewport.name}`,
          description: 'Approval dialog viewport check',
          scheduled_at: new Date(Date.now() + 86400000).toISOString(),
          tournament_name: `Approval Viewport Tournament ${viewport.name}`,
          tournament_league: eventInfo.leaguePk,
          tournament_type: 'single_elimination',
          timezone: 'America/New_York',
        },
      );
      expect(createResp.ok()).toBeTruthy();
      const event = await createResp.json();

      await loginEventPlayer(context);
      const rsvpResp = await postWithCsrf(
        context,
        `${API_URL}/events/${event.id}/signup/`,
        { intent: 'rsvp' },
      );
      expect(rsvpResp.ok()).toBeTruthy();
      const signup = await rsvpResp.json();

      // Prior 2,400 vs self-report 3,200 renders the large-change warning.
      await setApprovedMmr(context, eventInfo.orgPk, 5001, 2400);

      await loginEventAdmin(context);
      await visitAndWaitForHydration(page, `/events/${event.id}`);
      await page.getByTestId('event-tab-signups').click();
      await expect(
        page.getByTestId(`event-signup-row-${signup.id}`),
      ).toBeVisible({ timeout: 10000 });
      await page.getByTestId(`approve-signup-${signup.id}`).click();

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5000 });
      // The signups tab is desktop-only chrome; resize once the dialog is open.
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await expect(dialog.getByTestId('mmr-delta')).toBeVisible();

      await expect(dialog).toBeInViewport({ ratio: 1 });

      // No scrolling: every action is fully on screen as soon as it opens.
      for (const testId of [
        'mmr-modal-approve',
        'mmr-modal-reject',
        'mmr-modal-close',
      ]) {
        await expect(dialog.getByTestId(testId)).toBeInViewport({ ratio: 1 });
      }

      await dialog.getByTestId('mmr-modal-close').click();
      await expect(dialog).not.toBeVisible();
    });
  }
});
