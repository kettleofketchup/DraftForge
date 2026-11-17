/**
 * Stubs third-party APIs the app calls from the browser, so E2E never
 * depends on them (e.g. GitHub's unauthenticated rate limit returning 403).
 *
 * Reference: docs/testing/auth/fixtures.md
 */

import type { Browser, BrowserContext } from '@playwright/test';
import { test as base } from '@playwright/test';

// Every stubbed response carries it, so a spec can tell a stub from a real third-party hit.
export const STUB_HEADER = 'x-e2e-stub';

export const GITHUB_API_PATTERN = 'https://api.github.com/**';
export const STUB_GITHUB_STARS = 42;
// api.github.com sends this; the app fetches it cross-origin.
export const GITHUB_CORS_HEADERS = { 'Access-Control-Allow-Origin': '*' };

// Hosts the app loads <img> content from. A real fetch puts CDN latency into every spec that
// waits for images, such as the layout sweep's settle check.
export const IMAGE_HOST_PATTERNS = [
  'https://assets.kettle.sh/**',
  'https://ui-avatars.com/**',
  'https://cdn.discordapp.com/**',
  'https://cdn.cloudflare.steamstatic.com/**',
];
const STUB_IMAGE_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 16 9">' +
  '<rect width="16" height="9" fill="#888"/></svg>';

export async function stubExternalApis(context: BrowserContext): Promise<void> {
  await context.route(GITHUB_API_PATTERN, (route) =>
    route.fulfill({
      status: 200,
      headers: { ...GITHUB_CORS_HEADERS, [STUB_HEADER]: '1' },
      contentType: 'application/json',
      body: JSON.stringify({ stargazers_count: STUB_GITHUB_STARS }),
    }),
  );
  for (const pattern of IMAGE_HOST_PATTERNS) {
    await context.route(pattern, (route) =>
      route.request().resourceType() === 'image'
        ? route.fulfill({
            status: 200,
            headers: { [STUB_HEADER]: '1' },
            contentType: 'image/svg+xml',
            body: STUB_IMAGE_SVG,
          })
        : route.fulfill({ status: 404, headers: { [STUB_HEADER]: '1' } }),
    );
  }
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
