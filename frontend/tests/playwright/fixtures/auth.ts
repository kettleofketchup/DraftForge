import { test as base, expect, BrowserContext, Page } from '@playwright/test';

// Use nginx hostname inside Docker containers, localhost for local runs
const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;

/**
 * Authentication utilities for Playwright tests.
 * Ports the Cypress login commands to Playwright.
 */

export interface UserInfo {
  pk: number;
  username: string;
  discordUsername?: string;
  discordId?: string;
  mmr?: number;
}

export interface LoginResponse {
  success: boolean;
  user: UserInfo;
}

/**
 * Login as a specific user by primary key.
 * Sets session cookies in the provided context.
 */
export async function loginAsUser(
  context: BrowserContext,
  userPk: number
): Promise<LoginResponse> {
  const response = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: userPk },
    headers: { 'Content-Type': 'application/json' },
  });

  expect(response.ok()).toBeTruthy();
  const data = await response.json();

  // Extract cookies from response headers and set them
  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }

  return data;
}

/**
 * Login as a specific user by Discord ID.
 * Discord IDs are stable across populate runs.
 */
export async function loginAsDiscordId(
  context: BrowserContext,
  discordId: string
): Promise<LoginResponse> {
  const response = await context.request.post(
    `${API_URL}/tests/login-as-discord/`,
    {
      data: { discord_id: discordId },
      headers: { 'Content-Type': 'application/json' },
    }
  );

  expect(response.ok()).toBeTruthy();
  const data = await response.json();

  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }

  return data;
}

/**
 * Login as admin user.
 */
export async function loginAdmin(context: BrowserContext): Promise<void> {
  const response = await context.request.post(`${API_URL}/tests/login-admin/`);
  expect(response.ok()).toBeTruthy();

  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }
}

/**
 * Login as staff user.
 */
export async function loginStaff(context: BrowserContext): Promise<void> {
  const response = await context.request.post(`${API_URL}/tests/login-staff/`);
  expect(response.ok()).toBeTruthy();

  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }
}

/**
 * Login as regular user.
 */
export async function loginUser(context: BrowserContext): Promise<void> {
  const response = await context.request.post(`${API_URL}/tests/login-user/`);
  expect(response.ok()).toBeTruthy();

  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }
}

/**
 * Parse and set session cookies from response headers.
 */
async function setSessionCookies(
  context: BrowserContext,
  cookieHeader: string
): Promise<void> {
  // Parse multiple cookies from header
  const cookieStrings = cookieHeader.split(/,(?=\s*\w+=)/);

  for (const cookieStr of cookieStrings) {
    const [nameValue] = cookieStr.split(';');
    const [name, value] = nameValue.split('=');

    if (name && value) {
      await context.addCookies([
        {
          name: name.trim(),
          value: value.trim(),
          domain: DOCKER_HOST,
          path: '/',
          secure: true,
          httpOnly: name.trim() === 'sessionid',
          sameSite: 'Lax',
        },
      ]);
    }
  }
}

/**
 * Wait for React hydration to complete.
 */
export async function waitForHydration(page: Page): Promise<void> {
  // Wait for body to be visible
  await page.locator('body').waitFor({ state: 'visible' });

  // Wait for document ready state
  await page.waitForFunction(() => document.readyState === 'complete');

  // Wait for React app indicators
  await page
    .locator('[data-slot], nav, main, #root')
    .first()
    .waitFor({ state: 'visible', timeout: 10000 });

  // Brief wait for React hydration
  await page.waitForTimeout(200);
}

/**
 * Visit a URL and wait for hydration.
 */
export async function visitAndWait(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await waitForHydration(page);
}

// Extended test fixture with auth helpers
export const test = base.extend<{
  loginAsUser: (userPk: number) => Promise<LoginResponse>;
  loginAsDiscordId: (discordId: string) => Promise<LoginResponse>;
  loginAdmin: () => Promise<void>;
  loginStaff: () => Promise<void>;
  loginUser: () => Promise<void>;
  waitForHydration: () => Promise<void>;
  visitAndWait: (url: string) => Promise<void>;
}>({
  // Override context to inject playwright marker (disables react-scan)
  context: async ({ context }, use) => {
    // Add init script that runs before any page content loads
    // This sets window.playwright = true which react-scan checks
    await context.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    await use(context);
  },
  loginAsUser: async ({ context }, use) => {
    await use((userPk: number) => loginAsUser(context, userPk));
  },
  loginAsDiscordId: async ({ context }, use) => {
    await use((discordId: string) => loginAsDiscordId(context, discordId));
  },
  loginAdmin: async ({ context }, use) => {
    await use(() => loginAdmin(context));
  },
  loginStaff: async ({ context }, use) => {
    await use(() => loginStaff(context));
  },
  loginUser: async ({ context }, use) => {
    await use(() => loginUser(context));
  },
  waitForHydration: async ({ page }, use) => {
    await use(() => waitForHydration(page));
  },
  visitAndWait: async ({ page }, use) => {
    await use((url: string) => visitAndWait(page, url));
  },
});

export { expect } from '@playwright/test';
