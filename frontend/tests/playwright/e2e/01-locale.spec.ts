// Import from project fixtures (provides waitForHydration, sets
// window.playwright = true to disable react-scan, and exposes login helpers).
import { test, expect, loginUser } from '../fixtures';
import type { Page } from '@playwright/test';

// i18n hydration bugs must surface immediately; no retries here.
test.describe.configure({ retries: 0 });

const LOGIN_BUTTON = '[data-testid="navbarLoginButton"]';
const LOGOUT_BUTTON = '[data-testid="navbarLogoutButton"]';
const PROFILE_BUTTON = '[data-testid="navbarProfileButton"]';
const USER_AVATAR = 'header [data-testid="user-avatar"]';
const ES_LOGIN = 'Iniciar sesión con Discord';
const EN_LOGIN = 'Login with Discord';

// Helper: attach hydration-error capture to a freshly created page.
// Used by both default-page tests and tests that build their own context.
function attachErrorCapture(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text()}`);
  });
  return errors;
}

test.describe('navbar i18n — anonymous', () => {
  test('?lang=es renders Spanish login + correct <html lang>', async ({ page }) => {
    const errors = attachErrorCapture(page);
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    expect(errors, 'unexpected runtime errors').toEqual([]);
  });

  test('?lang=es writes df-locale cookie even on prerendered /', async ({ page, context }) => {
    const errors = attachErrorCapture(page);
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    const cookies = await context.cookies();
    const dfLocale = cookies.find((c) => c.name === 'df-locale');
    expect(dfLocale?.value).toBe('es');
    expect(errors).toEqual([]);
  });

  test('cookie persists Spanish across navigation', async ({ page }) => {
    const errors = attachErrorCapture(page);
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    expect(errors).toEqual([]);
  });

  test('default en-US context renders English', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'en-US' });
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    await page.goto('/');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    expect(errors).toEqual([]);
    await ctx.close();
  });

  test('es-ES context renders Spanish navbar + aria-labels', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    // Aria-label regression check.
    await expect(
      page.locator('[aria-label="Documentación"]').first(),
    ).toBeVisible();
    expect(errors).toEqual([]);
    await ctx.close();
  });

  test('unsupported locale (fr-FR) falls back to English', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'fr-FR' });
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    expect(errors).toEqual([]);
    await ctx.close();
  });

  test('?lang=en beats df-locale=es cookie', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'en-US' });
    await ctx.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    await page.goto('/tournaments?lang=en');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    expect(errors).toEqual([]);
    await ctx.close();
  });

  test('clearing df-locale falls back to Accept-Language (en-US → English)', async ({ browser }) => {
    // Sets cookie=es, asserts Spanish; clears cookie, asserts fallback to the
    // context's Accept-Language (en-US) → English. The cookie's clear behavior
    // is the actual subject; locale doesn't change between p1 and p2.
    const ctx = await browser.newContext({ locale: 'en-US' });
    await ctx.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const p1 = await ctx.newPage();
    const errorsP1 = attachErrorCapture(p1);
    await p1.goto('/tournaments');
    await expect(p1.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    expect(errorsP1).toEqual([]);
    await ctx.clearCookies();
    const p2 = await ctx.newPage();
    const errorsP2 = attachErrorCapture(p2);
    await p2.goto('/tournaments');
    await expect(p2.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    expect(errorsP2).toEqual([]);
    await ctx.close();
  });

  test('dynamic route SSR ships Spanish HTML (no flicker for es-ES)', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    const response = await page.goto('/tournaments');
    const html = (await response?.text()) ?? '';
    expect(html).toContain(ES_LOGIN);
    expect(errors).toEqual([]);
    await ctx.close();
  });

  test('prerendered / ships English HTML then swaps to Spanish (documented trade-off)', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    const response = await page.goto('/');
    const html = (await response?.text()) ?? '';
    expect(html).toContain(EN_LOGIN);
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    expect(errors).toEqual([]);
    await ctx.close();
  });
});

test.describe('navbar i18n — authenticated', () => {
  test('logged-in es-ES context shows Cerrar sesión and Perfil', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    await loginUser(ctx);
    const page = await ctx.newPage();
    const errors = attachErrorCapture(page);
    await page.goto('/tournaments');
    // Open the user dropdown using the existing user-avatar testid scoped to navbar.
    await page.locator(USER_AVATAR).first().click();
    await expect(page.locator(LOGOUT_BUTTON)).toBeVisible();
    await expect(page.locator(LOGOUT_BUTTON)).toHaveText('Cerrar sesión');
    await expect(page.locator(PROFILE_BUTTON)).toHaveText('Perfil');
    expect(errors).toEqual([]);
    await ctx.close();
  });
});
