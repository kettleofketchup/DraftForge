/**
 * Event Signup Form E2E Tests
 *
 * Covers the new EventSignupModal:
 *   - Skip-the-form fast path (complete profile bypasses modal)
 *   - Modal opens for incomplete profile with all expected sections
 *   - rank_status="never" reveals Battle Cup Tier (not Medal/Star)
 *   - Screenshot-required event surfaces URL field
 *   - Tentative path uses same modal with different submit label
 *   - Friend ID universal across game types (Deadlock event)
 *   - Upgrade tentative -> rsvp re-runs gap evaluation
 *   - Mobile viewport renders Sheet variant with sticky submit
 *
 * Notes
 *   - Fast-path / upgrade tests use `E2E Signup Event` because event_player_1's
 *     populate profile (active rank, Legend 3, positions, no Friend ID required)
 *     satisfies that event's requirements. The screenshot/Deadlock events require
 *     unverified_friend_id which is not seeded — so fast-path against them would
 *     always open the modal regardless of intent.
 *   - Modal-presence tests use the screenshot/Deadlock events plus the
 *     no-profile player to guarantee the modal opens.
 */

import { test, expect, type BrowserContext } from '@playwright/test';
import {
  loginEventPlayer,
  loginEventPlayerNoProfile,
  getEventsTestData,
  resetEventsData,
  type EventInfo,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

async function getEventByName(context: BrowserContext, name: string): Promise<number> {
  const resp = await context.request.get(
    `${API_URL}/events/?search=${encodeURIComponent(name)}`,
  );
  if (!resp.ok()) throw new Error(`Event lookup failed: ${resp.status()}`);
  const data = (await resp.json()) as
    | Array<{ id?: number; pk?: number; name: string }>
    | { results: Array<{ id?: number; pk?: number; name: string }> };
  const events = Array.isArray(data) ? data : data.results;
  const found = events.find((e) => e.name === name);
  if (!found) throw new Error(`Event not found: ${name}. Run just db::populate::all`);
  const id = found.pk ?? found.id;
  if (id == null) throw new Error(`Event '${name}' has no pk/id field`);
  return id;
}

let eventInfo: EventInfo;

test.describe('Event Signup Form (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    // Reset signups between tests so state from a previous run (rsvp/tentative)
    // doesn't change which buttons are visible on the event page.
    await resetEventsData(context);
  });

  test('complete profile uses fast path (no modal)', async ({ page, context }) => {
    await loginEventPlayer(context);
    // event_player_1 has rank_status=active, rank_medal=Legend 3, positions set,
    // and rank_screenshot — complete for E2E Signup Event (Dota 2, no extras).
    await page.goto(`/events/${eventInfo.pk}`);
    await page.getByTestId('event-signup-btn').click();
    // Fast path: no modal opens, the signup is created, and the cancel button
    // appears in its place.
    await expect(page.getByTestId('event-signup-modal')).toHaveCount(0);
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
  });

  test('incomplete profile opens modal with all sections', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Dota Event With Screenshot');
    await page.goto(`/events/${eventId}`);
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await expect(modal.getByTestId('signup-friend-id')).toBeVisible();
    await expect(modal.getByTestId('signup-rank-status')).toBeVisible();
    await expect(modal.getByTestId('signup-positions')).toBeVisible();
  });

  test('rank_status="never" reveals Battle Cup Tier (not Medal/Star)', async ({
    page,
    context,
  }) => {
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Dota Event With Screenshot');
    await page.goto(`/events/${eventId}`);
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await modal.getByText("I've never had an MMR").click();
    await expect(modal.getByTestId('signup-battlecup-tier')).toBeVisible();
    await expect(modal.getByTestId('signup-rank-medal')).toHaveCount(0);
    await expect(modal.getByTestId('signup-rank-star')).toHaveCount(0);
  });

  test('screenshot-required event surfaces URL field', async ({ page, context }) => {
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Dota Event With Screenshot');
    await page.goto(`/events/${eventId}`);
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await modal.getByText('I have an active MMR').click();
    await modal.getByTestId('signup-rank-medal').click();
    await page.getByRole('option', { name: 'Legend', exact: true }).click();
    await modal.getByTestId('signup-rank-star').click();
    await page.getByRole('option', { name: 'Star 1', exact: true }).click();
    await expect(modal.getByTestId('signup-screenshot-url')).toBeVisible();
  });

  test('tentative path uses same modal with different submit label', async ({
    page,
    context,
  }) => {
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Dota Event With Screenshot');
    await page.goto(`/events/${eventId}`);
    await page.getByTestId('event-tentative-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await expect(modal.getByTestId('event-signup-submit-btn')).toContainText('Mark Tentative');
  });

  test('Friend ID universal across game types (Deadlock event)', async ({
    page,
    context,
  }) => {
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Deadlock Event');
    await page.goto(`/events/${eventId}`);
    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    await expect(modal.getByTestId('signup-friend-id')).toBeVisible();
    // Non-Dota game: rank-status / positions sections must not render.
    await expect(modal.getByTestId('signup-rank-status')).toHaveCount(0);
    await expect(modal.getByTestId('signup-positions')).toHaveCount(0);
  });

  test('upgrade tentative to rsvp re-runs gap evaluation', async ({ page, context }) => {
    // event_player_1's profile is complete for E2E Signup Event, so both the
    // tentative button AND the upgrade-to-rsvp button take the fast path.
    await loginEventPlayer(context);
    await page.goto(`/events/${eventInfo.pk}`);
    await page.getByTestId('event-tentative-btn').click();
    await expect(page.getByTestId('event-cancel-tentative-btn')).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId('event-upgrade-rsvp-btn')).toBeVisible();
    await page.getByTestId('event-upgrade-rsvp-btn').click();
    await expect(page.getByTestId('event-cancel-rsvp-btn')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('event-cancel-tentative-btn')).toHaveCount(0);
  });

  test('mobile viewport renders Sheet variant with sticky submit', async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await loginEventPlayerNoProfile(context);
    const eventId = await getEventByName(context, 'Test Dota Event With Screenshot');
    await page.goto(`/events/${eventId}`);
    // The signup button is testid-tagged regardless of nav state.
    const signupBtn = page.getByTestId('event-signup-btn');
    await signupBtn.scrollIntoViewIfNeeded();
    await signupBtn.click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    // Sticky submit footer must remain in viewport without scrolling.
    await expect(modal.getByTestId('event-signup-submit-btn')).toBeInViewport();
  });
});
