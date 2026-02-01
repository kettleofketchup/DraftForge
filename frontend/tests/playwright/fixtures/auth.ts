import { test as base, expect, BrowserContext, Page } from '@playwright/test';

// Use localhost by default (matches playwright.config.ts baseURL)
// Can be overridden with DOCKER_HOST for running inside Docker containers
export const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
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
  const url = `${API_URL}/tests/login-as/`;
  console.log(`[auth] loginAsUser: POST ${url} (user_pk=${userPk})`);

  let response;
  try {
    response = await context.request.post(url, {
      data: { user_pk: userPk },
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e) {
    console.error(`[auth] loginAsUser: Network error - ${e}`);
    throw new Error(`loginAsUser network error: ${e}`);
  }

  const status = response.status();
  console.log(`[auth] loginAsUser response: ${status}`);

  if (!response.ok()) {
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '[could not read body]';
    }
    const headers = response.headers();
    console.error(`[auth] loginAsUser FAILED: ${status}`);
    console.error(`[auth] Response headers: ${JSON.stringify(headers)}`);
    console.error(`[auth] Response body: ${body}`);
    throw new Error(`loginAsUser failed: ${status} - ${body.slice(0, 500)}`);
  }

  const data = await response.json();
  console.log(`[auth] loginAsUser: OK - logged in as ${data.user?.username}`);

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
  const url = `${API_URL}/tests/login-as-discord/`;
  console.log(`[auth] loginAsDiscordId: POST ${url} (discord_id=${discordId})`);

  const response = await context.request.post(url, {
    data: { discord_id: discordId },
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok()) {
    const status = response.status();
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '[could not read body]';
    }
    console.error(`[auth] loginAsDiscordId FAILED: ${status} - ${body}`);
    throw new Error(
      `loginAsDiscordId failed: ${status} - ${body.slice(0, 500)}`
    );
  }

  const data = await response.json();
  console.log(
    `[auth] loginAsDiscordId: OK - logged in as ${data.user?.username}`
  );

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
  const url = `${API_URL}/tests/login-admin/`;
  console.log(`[auth] loginAdmin: POST ${url}`);
  console.log(`[auth] Environment: API_URL=${API_URL}, DOCKER_HOST=${DOCKER_HOST}, CI=${process.env.CI}`);

  let response;
  try {
    response = await context.request.post(url);
  } catch (e) {
    console.error(`[auth] loginAdmin: Network error connecting to ${url}`);
    console.error(`[auth] Error: ${e}`);
    throw new Error(`loginAdmin network error: ${e}`);
  }

  const status = response.status();
  const statusText = response.statusText();
  const headers = response.headers();

  console.log(`[auth] loginAdmin response: ${status} ${statusText}`);
  console.log(`[auth] Response headers: ${JSON.stringify(headers, null, 2)}`);

  if (!response.ok()) {
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '[could not read body]';
    }
    console.error(`[auth] loginAdmin FAILED: ${status} ${statusText}`);
    console.error(`[auth] Response body: ${body}`);
    console.error(`[auth] This usually means:`);
    console.error(`[auth]   - 403: TEST=true not set or IP not whitelisted`);
    console.error(`[auth]   - 404: Backend not running or route not found`);
    console.error(`[auth]   - 502/503: Nginx can't reach backend`);
    throw new Error(
      `loginAdmin failed: ${status} ${statusText} - ${body.slice(0, 500)}`
    );
  }

  console.log(`[auth] loginAdmin: OK`);
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
  const url = `${API_URL}/tests/login-staff/`;
  console.log(`[auth] loginStaff: POST ${url}`);

  const response = await context.request.post(url);

  if (!response.ok()) {
    const status = response.status();
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '[could not read body]';
    }
    console.error(`[auth] loginStaff FAILED: ${status} - ${body}`);
    throw new Error(`loginStaff failed: ${status} - ${body.slice(0, 500)}`);
  }

  console.log(`[auth] loginStaff: OK (${response.status()})`);

  const cookies = response.headers()['set-cookie'];
  if (cookies) {
    await setSessionCookies(context, cookies);
  }
}

/**
 * Login as regular user.
 */
export async function loginUser(context: BrowserContext): Promise<void> {
  const url = `${API_URL}/tests/login-user/`;
  console.log(`[auth] loginUser: POST ${url}`);

  const response = await context.request.post(url);

  if (!response.ok()) {
    const status = response.status();
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '[could not read body]';
    }
    console.error(`[auth] loginUser FAILED: ${status} - ${body}`);
    throw new Error(`loginUser failed: ${status} - ${body.slice(0, 500)}`);
  }

  console.log(`[auth] loginUser: OK (${response.status()})`);

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
