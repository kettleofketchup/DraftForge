import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * Patterns for console messages that should be ignored during tests.
 * These are typically hydration warnings or font loading errors that
 * don't indicate actual test failures.
 */
export const IGNORED_CONSOLE_PATTERNS: readonly string[] = [
  // React hydration warnings
  'Hydration failed',
  'Text content does not match',
  'Warning: Text content did not match',
  "server rendered HTML didn't match the client",
  'Expected server HTML to contain',
  // Network/resource errors
  'net::ERR_ABORTED',
  'Failed to load resource',
  // Font loading
  'fonts.googleapis.com',
  'font',
  // Additional hydration patterns
  'Hydration',
  'server HTML',
] as const;

/**
 * Check if a console message should be ignored based on known patterns.
 *
 * @param message - The console message text to check
 * @returns true if the message matches an ignored pattern
 */
export function shouldIgnoreConsoleMessage(message: string): boolean {
  const lowerMessage = message.toLowerCase();
  return IGNORED_CONSOLE_PATTERNS.some((pattern) =>
    lowerMessage.includes(pattern.toLowerCase())
  );
}

/**
 * Visit a page and wait for React hydration to complete.
 * Waits for the body to be visible and allows time for React to hydrate.
 *
 * @param page - Playwright Page instance
 * @param url - URL to navigate to
 */
export async function visitAndWaitForHydration(
  page: Page,
  url: string
): Promise<void> {
  await page.goto(url);

  // Wait for the body to be visible
  await page.locator('body').waitFor({ state: 'visible' });

  // Wait for DOMContentLoaded which indicates initial HTML is parsed
  await page.waitForLoadState('domcontentloaded');

  // Give React a moment to hydrate (short timeout instead of networkidle
  // since the app may have polling/websockets that keep network active)
  await page.waitForTimeout(500);

  // Final check that body is still visible after hydration
  await page.locator('body').waitFor({ state: 'visible' });
}

/**
 * Wait for any loading states to complete.
 * Checks for common loading indicators and waits for them to disappear.
 *
 * @param page - Playwright Page instance
 * @param timeout - Maximum time to wait for loading to complete (default: 10000ms)
 */
export async function waitForLoadingToComplete(
  page: Page,
  timeout = 10000
): Promise<void> {
  const loadingSelector =
    '[data-testid="loading"], .loading, .spinner, [aria-busy="true"]';

  // Check if any loading indicators exist
  const loadingCount = await page.locator(loadingSelector).count();

  if (loadingCount > 0) {
    // Wait for all loading indicators to disappear
    await page.locator(loadingSelector).first().waitFor({
      state: 'hidden',
      timeout,
    });
  }
}

/**
 * Smart navigation that handles both visible links and dropdown menus.
 * Attempts to click visible navigation links first, then tries dropdown menus,
 * and falls back to direct navigation if no UI is found.
 *
 * @param page - Playwright Page instance
 * @param route - The route/path to navigate to (e.g., '/about')
 */
export async function navigateToRoute(page: Page, route: string): Promise<void> {
  // Try to find visible navigation links first
  const visibleLinkSelectors = [
    `nav a[href="${route}"]`,
    `header a[href="${route}"]`,
    `.navbar a[href="${route}"]`,
    `a[href="${route}"]`,
  ];

  for (const selector of visibleLinkSelectors) {
    const link = page.locator(selector).first();
    const isVisible = await link.isVisible().catch(() => false);

    if (isVisible) {
      await link.click();
      await page.waitForURL(`**${route}*`);
      return;
    }
  }

  // If no visible links, try dropdown navigation (mobile menus, etc.)
  const dropdownTriggers = [
    'button[aria-haspopup="true"]',
    '.dropdown-toggle',
    'button:has-text("Menu")',
    '.menu-button',
    '[data-testid="menu-button"]',
    '.hamburger-menu',
    '[data-testid="mobile-menu-button"]',
  ];

  for (const triggerSelector of dropdownTriggers) {
    const trigger = page.locator(triggerSelector).first();
    const isVisible = await trigger.isVisible().catch(() => false);

    if (isVisible) {
      await trigger.click();

      // Wait for dropdown to open
      await page.waitForTimeout(300);

      // Try to click the navigation link now that dropdown is open
      const dropdownLink = page.locator(`a[href="${route}"]`).first();
      const linkVisible = await dropdownLink.isVisible().catch(() => false);

      if (linkVisible) {
        await dropdownLink.click();
        await page.waitForURL(`**${route}*`);
        return;
      }
    }
  }

  // Fallback: direct navigation if no UI navigation found
  console.log(`No navigation UI found for ${route}, using direct navigation`);
  await visitAndWaitForHydration(page, route);
}

/**
 * Check for basic accessibility features with flexible expectations.
 * Verifies essential a11y requirements like language attribute, page title,
 * and main landmark. Logs warnings for non-critical issues.
 *
 * @param page - Playwright Page instance
 */
export async function checkBasicAccessibility(page: Page): Promise<void> {
  // Check language attribute exists
  const htmlElement = page.locator('html');
  await expect(htmlElement).toHaveAttribute('lang', /.+/);

  // Check for page title
  const title = await page.title();
  expect(title.length).toBeGreaterThan(0);

  // Check for main content landmark
  const mainLandmark = page.locator('main, [role="main"]');
  const hasMainLandmark = (await mainLandmark.count()) > 0;

  if (hasMainLandmark) {
    await expect(mainLandmark.first()).toBeVisible();
  } else {
    console.log(
      'No main landmark found - this could be improved for accessibility'
    );
  }

  // Check that buttons have accessible names
  const buttons = page.locator('button');
  const buttonCount = await buttons.count();

  for (let i = 0; i < buttonCount; i++) {
    const button = buttons.nth(i);
    const isVisible = await button.isVisible().catch(() => false);

    if (isVisible) {
      const text = await button.textContent();
      const ariaLabel = await button.getAttribute('aria-label');
      const ariaLabelledBy = await button.getAttribute('aria-labelledby');

      const hasAccessibleName =
        (text && text.trim().length > 0) || ariaLabel || ariaLabelledBy;

      if (!hasAccessibleName) {
        const outerHTML = await button.evaluate((el) => el.outerHTML);
        console.log(`Button without accessible name found: ${outerHTML}`);
      }
    }
  }

  // Check that links have accessible names
  const links = page.locator('a');
  const linkCount = await links.count();

  for (let i = 0; i < linkCount; i++) {
    const link = links.nth(i);
    const isVisible = await link.isVisible().catch(() => false);

    if (isVisible) {
      const text = await link.textContent();
      const ariaLabel = await link.getAttribute('aria-label');

      const hasAccessibleName =
        (text && text.trim().length > 0) || ariaLabel;

      if (!hasAccessibleName) {
        const outerHTML = await link.evaluate((el) => el.outerHTML);
        console.log(`Link without accessible name found: ${outerHTML}`);
      }
    }
  }

  // Check that form inputs have labels
  const inputs = page.locator('input:not([type="hidden"])');
  const inputCount = await inputs.count();

  for (let i = 0; i < inputCount; i++) {
    const input = inputs.nth(i);
    const isVisible = await input.isVisible().catch(() => false);

    if (isVisible) {
      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const ariaLabelledBy = await input.getAttribute('aria-labelledby');

      let hasLabel = false;
      if (id) {
        const labelForInput = page.locator(`label[for="${id}"]`);
        hasLabel = (await labelForInput.count()) > 0;
      }

      const hasAccessibleName = hasLabel || ariaLabel || ariaLabelledBy;

      if (!hasAccessibleName) {
        const outerHTML = await input.evaluate((el) => el.outerHTML);
        console.log(`Input without label found: ${outerHTML}`);
      }
    }
  }
}
