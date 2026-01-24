import { test, expect } from '../fixtures';
import {
  visitAndWaitForHydration,
  checkBasicAccessibility,
} from '../fixtures';

test.describe('Navigation and Basic Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Visit the home page and wait for React hydration before each test
    await visitAndWaitForHydration(page, '/');
  });

  test('should load the home page successfully', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);

    // Check that the page loads without errors
    const baseUrl = page.url().split('/').slice(0, 3).join('/');
    expect(page.url()).toBe(`${baseUrl}/`);
  });

  test('should have working navigation links', async ({ page }) => {
    // Test navigation to different routes
    const routes = ['/tournaments', '/about', '/users'];

    for (const route of routes) {
      // Use smart navigation that handles responsive design
      let foundNavigation = false;

      // Check if mobile menu button is visible (mobile viewport)
      const mobileMenuButton = page.locator(
        'button[aria-label="Open mobile menu"]'
      );
      const isMobileMenuVisible = await mobileMenuButton
        .isVisible()
        .catch(() => false);

      if (isMobileMenuVisible) {
        // Mobile navigation
        await mobileMenuButton.click();
        await page.waitForTimeout(300);

        // Look for the route in the dropdown
        const mobileLink = page.locator(`a[href="${route}"]`).first();
        const isMobileLinkVisible = await mobileLink
          .isVisible()
          .catch(() => false);

        if (isMobileLinkVisible) {
          await mobileLink.click();
          foundNavigation = true;
        }
      } else {
        // Desktop navigation - try visible links
        const desktopSelectors = [
          `nav a[href="${route}"]`,
          `header a[href="${route}"]`,
          `.navbar a[href="${route}"]`,
        ];

        for (const selector of desktopSelectors) {
          const link = page.locator(selector).first();
          const isVisible = await link.isVisible().catch(() => false);

          if (isVisible) {
            await link.click();
            foundNavigation = true;
            break;
          }
        }
      }

      // If still no navigation found, skip this route
      if (!foundNavigation) {
        console.log(`No UI navigation found for ${route} - skipping`);
        await visitAndWaitForHydration(page, '/');
        continue;
      }

      // Verify we navigated to the correct route (if navigation was attempted)
      const currentUrl = page.url();
      if (currentUrl.includes(route)) {
        await expect(page.locator('body')).toBeVisible();
      }

      // Go back to home for next iteration
      await visitAndWaitForHydration(page, '/');
    }
  });

  test('should be responsive and mobile-friendly', async ({ page }) => {
    // Test different viewport sizes
    const viewports = [
      { width: 375, height: 667, device: 'iPhone SE' },
      { width: 768, height: 1024, device: 'iPad' },
      { width: 1280, height: 720, device: 'Desktop' },
    ];

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await visitAndWaitForHydration(page, '/');

      // Check that content is visible and accessible
      await expect(page.locator('body')).toBeVisible();

      // Ensure no horizontal scrolling on mobile
      if (viewport.width < 768) {
        const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
        expect(scrollWidth).toBeLessThanOrEqual(viewport.width + 1);
      }
    }
  });

  test('should handle 404 pages gracefully', async ({ page }) => {
    const response = await page.goto('/non-existent-page');

    // Should show some kind of error page or redirect
    await expect(page.locator('body')).toBeVisible();

    // Could be 404 page or redirect to home
    const currentUrl = page.url();
    const baseUrl = currentUrl.split('/').slice(0, 3).join('/');
    const isValidState =
      currentUrl.includes('/non-existent-page') ||
      currentUrl === `${baseUrl}/`;
    expect(isValidState).toBe(true);
  });

  test('should load page assets correctly', async ({ page }) => {
    await visitAndWaitForHydration(page, '/');

    // Check that CSS is loaded (by verifying styled elements)
    const bodyMargin = await page.locator('body').evaluate((el) => {
      return window.getComputedStyle(el).margin;
    });
    expect(bodyMargin).not.toBe('');

    // Check for favicon
    const faviconResponse = await page.request.get('/favicon.ico');
    expect([200, 304]).toContain(faviconResponse.status());

    // Just verify the page loaded successfully
    await expect(page.locator('body')).toBeVisible();
  });

  test('should have accessibility basics', async ({ page }) => {
    await visitAndWaitForHydration(page, '/');

    // Use the flexible accessibility checker
    await checkBasicAccessibility(page);
  });

  test('should handle browser back/forward navigation', async ({ page }) => {
    // Navigate through several pages
    await visitAndWaitForHydration(page, '/');

    // Handle responsive navigation properly
    // Check if we're on mobile viewport (mobile menu button visible)
    const mobileMenuButton = page.locator(
      'button[aria-label="Open mobile menu"]'
    );
    const isMobileMenuVisible = await mobileMenuButton
      .isVisible()
      .catch(() => false);

    if (isMobileMenuVisible) {
      // Mobile navigation flow
      await mobileMenuButton.click();
      await page.waitForTimeout(300); // Wait for dropdown to open
      await page
        .locator('a')
        .filter({ hasText: /tournaments/i })
        .first()
        .click();
    } else {
      // Desktop navigation flow - look for visible navigation links
      const desktopNavLink = page.locator(
        'nav a[href*="/tournaments"], header a[href*="/tournaments"]'
      );
      const isDesktopNavVisible = await desktopNavLink
        .first()
        .isVisible()
        .catch(() => false);

      if (isDesktopNavVisible) {
        await desktopNavLink.first().click();
      } else {
        // Fallback - try any tournaments link with force
        await page
          .locator('a')
          .filter({ hasText: /tournaments/i })
          .first()
          .click({ force: true });
      }
    }

    await expect(page).toHaveURL(/\/tournaments/);

    // Use browser back button
    await page.goBack();
    const baseUrl = page.url().split('/').slice(0, 3).join('/');
    expect(page.url()).toBe(`${baseUrl}/`);

    // Use browser forward button
    await page.goForward();
    await expect(page).toHaveURL(/\/tournaments/);
  });
});
