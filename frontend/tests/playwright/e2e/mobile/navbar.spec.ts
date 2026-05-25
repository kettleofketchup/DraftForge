/** Mobile navbar (#252): runs in mobile-pixel5/iphone13 projects. */

import { test, expect } from '../../fixtures';

const MOBILE_TOGGLE = '[data-testid="mobileNavToggle"]';

test.describe('Mobile navbar', () => {
  test('renders without horizontal overflow on home', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(MOBILE_TOGGLE)).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow, 'horizontal overflow on home').toBe(false);
  });

  test('desktop NavLinks stay hidden below md', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(MOBILE_TOGGLE)).toBeVisible();

    // nav-link-* belongs to the desktop NavLinks row (hidden md:flex).
    const desktopLink = page.locator('[data-testid^="nav-link-"]').first();
    await expect(desktopLink).toBeHidden();
  });

  test('hamburger opens the drawer and routes are reachable', async ({ page }) => {
    await page.goto('/');
    await page.locator(MOBILE_TOGGLE).click();

    const drawer = page.locator('[role="dialog"]').first();
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole('link', { name: /tournaments/i })).toBeVisible();
  });
});
