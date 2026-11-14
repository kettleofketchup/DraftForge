import { expect, test } from '../fixtures';
import {
  GITHUB_API_PATTERN,
  GITHUB_CORS_HEADERS,
  STUB_GITHUB_STARS,
} from '../fixtures/external-apis';

const STAR_COUNT = '[data-testid="githubStarCount"]';
const LOGIN_BUTTON = '[data-testid="navbarLoginButton"]';

test.describe('external API stubs @cicd', () => {
  test('default page gets the stubbed GitHub star count', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator(STAR_COUNT)).toHaveText(
      String(STUB_GITHUB_STARS),
    );
  });

  test('browser.newContext() gets the stub too', async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto('/');
    await expect(page.locator(STAR_COUNT)).toHaveText(
      String(STUB_GITHUB_STARS),
    );
    await ctx.close();
  });

  test('navbar survives a GitHub 403 and hides the star count', async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    await page.route(GITHUB_API_PATTERN, (route) =>
      route.fulfill({
        status: 403,
        headers: GITHUB_CORS_HEADERS,
        contentType: 'application/json',
        body: '{"message":"API rate limit exceeded"}',
      }),
    );
    const response = page.waitForResponse((r) =>
      r.url().startsWith('https://api.github.com/'),
    );
    await page.goto('/');
    expect((await response).status()).toBe(403);
    await expect(page.locator(LOGIN_BUTTON)).toBeVisible();
    await expect(page.locator(STAR_COUNT)).toHaveCount(0);
    expect(pageErrors).toEqual([]);
  });
});
