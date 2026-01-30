import { test as base, expect, BrowserContext, Page } from '@playwright/test';

// Use nginx hostname inside Docker containers, localhost for local runs
export const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
export const API_URL = `https://${DOCKER_HOST}/api`;

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
 * Login as admin user via context.request.
 * Note: Playwright's context.request automatically handles Set-Cookie headers.
 *
 * IMPORTANT: For cookies to work with page XHR requests, you should:
 * 1. Create a page first
 * 2. Navigate to a URL on the target domain
 * 3. Then call loginAdminFromPage() instead
 *
 * This function is kept for API-only tests where page XHR is not needed.
 */
export async function loginAdmin(context: BrowserContext): Promise<void> {
  const response = await context.request.post(`${API_URL}/tests/login-admin/`);
  expect(response.ok()).toBeTruthy();
  // Playwright automatically stores cookies from response - no manual handling needed
}

/**
 * Login as admin user from within a page context.
 * This ensures cookies are properly set in the browser's native cookie jar.
 * Use this when you need to make authenticated XHR requests from the page.
 */
export async function loginAdminFromPage(page: Page): Promise<void> {
  // Navigate to a page on the target domain first to establish origin
  const currentUrl = page.url();
  if (!currentUrl.includes(DOCKER_HOST)) {
    await page.goto(`https://${DOCKER_HOST}/`);
    await page.waitForLoadState('domcontentloaded');
  }

  // Make login request from within the page so browser handles cookies natively
  const result = await page.evaluate(async (apiUrl: string) => {
    const response = await fetch(`${apiUrl}/tests/login-admin/`, {
      method: 'POST',
      credentials: 'include',
    });
    return { ok: response.ok, status: response.status };
  }, API_URL);

  if (!result.ok) {
    throw new Error(`Login failed with status ${result.status}`);
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

  // Use URL instead of domain/path for more reliable cookie setting
  const cookieUrl = `https://${DOCKER_HOST}/`;

  for (const cookieStr of cookieStrings) {
    const [nameValue] = cookieStr.split(';');
    const [name, value] = nameValue.split('=');

    if (name && value) {
      await context.addCookies([
        {
          name: name.trim(),
          value: value.trim(),
          url: cookieUrl,  // Use URL instead of domain/path
          httpOnly: name.trim() === 'sessionid',
          // Note: sameSite defaults to 'Lax' when not specified
          // For same-origin requests, Lax should work
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
