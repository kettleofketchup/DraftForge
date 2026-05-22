import { test, expect, loginUser } from '../fixtures';
import type { Page } from '@playwright/test';

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 800 },
  { name: 'tablet', width: 768, height: 800 },
  { name: 'desktop', width: 1280, height: 800 },
];
const LOCALES = ['en', 'es'] as const;
const LOGIN_BUTTON = '[data-testid="navbarLoginButton"]';
const MOBILE_TOGGLE = '[data-testid="mobileNavToggle"]';
const USER_AVATAR = 'header [data-testid="user-avatar"]';
const LOGOUT_BUTTON = '[data-testid="navbarLogoutButton"]';

const EXPECTED_LOGIN = (locale: 'en' | 'es') =>
  locale === 'es' ? 'Iniciar sesión con Discord' : 'Login with Discord';

async function settleNavbar(page: Page, locale: 'en' | 'es') {
  await expect(page.locator(LOGIN_BUTTON)).toHaveText(EXPECTED_LOGIN(locale));
  await page.evaluate(() => document.fonts.ready);
}

// 1. First-paint matrix (3 viewports × 2 locales = 6)
for (const vp of VIEWPORTS) {
  for (const locale of LOCALES) {
    test(`first paint @ ${vp.name} ${locale}`, async ({ browser }) => {
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: locale === 'es' ? 'es-ES' : 'en-US',
      });
      const page = await ctx.newPage();
      await page.goto('/tournaments');
      await settleNavbar(page, locale);

      // Horizontal-overflow assertion at mobile width.
      if (vp.name === 'mobile') {
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        );
        expect(overflow, `horizontal overflow at ${vp.name} ${locale}`).toBe(false);
      }

      await page.screenshot({
        path: `screenshots/i18n/navbar-${vp.name}-${locale}.png`,
        fullPage: false,
      });
      await ctx.close();
    });
  }
}

// 2. Mobile drawer open (2)
for (const locale of LOCALES) {
  test(`mobile drawer open ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 375, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    await settleNavbar(page, locale);
    await page.locator(MOBILE_TOGGLE).click();
    // Verify the drawer actually opened before screenshotting.
    await expect(page.locator('[role="dialog"]').first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: `screenshots/i18n/mobile-drawer-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}

// 3. Logged-in user dropdown (2)
for (const locale of LOCALES) {
  test(`user dropdown @ desktop ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    await loginUser(ctx);
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    // After login, the navbar shows the user-avatar instead of the login
    // button — settleNavbar's login-text check would fail, so we settle on
    // the avatar element directly.
    await expect(page.locator(USER_AVATAR).first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.locator(USER_AVATAR).first().click();
    // Verify the dropdown actually opened.
    await expect(page.locator(LOGOUT_BUTTON)).toBeVisible();
    await page.screenshot({
      path: `screenshots/i18n/user-dropdown-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}

// 4. Focused login button (2)
for (const locale of LOCALES) {
  test(`focused login button @ desktop ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    const page = await ctx.newPage();
    await page.goto('/');
    await settleNavbar(page, locale);
    await page.locator(LOGIN_BUTTON).focus();
    await page.screenshot({
      path: `screenshots/i18n/login-focused-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}

// 5. Hover-revealed Tooltip on translated icon button (2)
// Navbar has icon buttons with aria-labels: Star us on GitHub, Documentation,
// Report a Bug. Hovering reveals a <TooltipContent>. This scenario captures
// the Documentation tooltip — translated in Task 15.
for (const locale of LOCALES) {
  const ariaLabel = locale === 'es' ? 'Documentación' : 'Documentation';
  test(`hover documentation tooltip @ desktop ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    const page = await ctx.newPage();
    await page.goto('/');
    await settleNavbar(page, locale);
    await page.locator(`[aria-label="${ariaLabel}"]`).first().hover();
    // Verify the tooltip rendered (Radix tooltips have role="tooltip").
    await expect(page.locator('[role="tooltip"]').first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: `screenshots/i18n/tooltip-docs-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}
