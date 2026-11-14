/**
 * Stubs third-party APIs the app calls from the browser, so E2E never
 * depends on them (e.g. GitHub's unauthenticated rate limit returning 403).
 *
 * Reference: docs/testing/auth/fixtures.md
 */

import type { Browser, BrowserContext } from '@playwright/test';
import { test as base } from '@playwright/test';

export const GITHUB_API_PATTERN = 'https://api.github.com/**';
export const STUB_GITHUB_STARS = 42;
// api.github.com sends this; the app fetches it cross-origin.
export const GITHUB_CORS_HEADERS = { 'Access-Control-Allow-Origin': '*' };

export async function stubExternalApis(context: BrowserContext): Promise<void> {
  await context.route(GITHUB_API_PATTERN, (route) =>
    route.fulfill({
      status: 200,
      headers: GITHUB_CORS_HEADERS,
      contentType: 'application/json',
      body: JSON.stringify({ stargazers_count: STUB_GITHUB_STARS }),
    }),
  );
}

// Wraps browser.newContext so every context gets the stubs: the built-in
// `context`/`page` fixtures and contexts specs create via browser.newContext().
export const test = base.extend<object, { browser: Browser }>({
  browser: [
    async ({ browser }, use) => {
      const newContext = browser.newContext.bind(browser);
      browser.newContext = async (options) => {
        const context = await newContext(options);
        await stubExternalApis(context);
        return context;
      };
      await use(browser);
      browser.newContext = newContext;
    },
    { scope: 'worker' },
  ],
});
