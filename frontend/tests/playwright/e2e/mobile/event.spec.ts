/**
 * Event detail page on mobile (#233).
 *
 * Asserts: breadcrumb hidden below sm:, no horizontal overflow with 6 tabs,
 * desktop TabsList hidden in favor of the page-nav dropdown.
 */

import { test, expect, getEventsTestData } from '../../fixtures';

test.describe('Event detail on mobile', () => {
  let eventPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const info = await getEventsTestData(context);
    eventPk = info.pk;
    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto(`/events/${eventPk}`);
    // Title is the cheapest anchor for "page loaded" on the event detail.
    await page.locator('h1').first().waitFor({ state: 'visible', timeout: 15_000 });
  });

  test('breadcrumb is hidden on mobile', async ({ page }) => {
    await expect(page.locator('nav[aria-label="breadcrumb"]')).toBeHidden();
  });

  test('no horizontal overflow on event detail', async ({ page }) => {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow, 'horizontal overflow on /events/:id').toBe(false);
  });

  test('desktop TabsList is hidden, page-nav dropdown drives tabs', async ({ page }) => {
    // The event page registers tabs via usePageNav, so the centered navbar
    // dropdown picks them up. The inline TabsList stays hidden md:inline-flex.
    await expect(page.locator('[data-testid="event-tab-details"]')).toBeHidden();
    await expect(page.locator('[data-testid="page-nav-trigger"]')).toBeVisible();
  });
});
