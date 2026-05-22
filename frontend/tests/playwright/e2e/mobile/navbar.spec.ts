/**
 * Mobile navbar — no squish (#252).
 *
 * Runs in mobile-pixel5 + mobile-iphone13 projects. The project's `use.device`
 * sets the viewport, user-agent, and touch flag; we don't call setViewportSize
 * here. The desktop navbar now switches in at lg (1024px); below lg, only the
 * hamburger drawer is visible.
 */

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

    // Any nav link with data-testid="nav-link-*" is the desktop NavLinks row.
    // It is `hidden md:flex` so should not be visible at mobile widths.
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
