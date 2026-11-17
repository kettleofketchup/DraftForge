import { expect, loginAdmin, test } from '../fixtures';
import { BASE_URL } from '../fixtures/base-url';
import {
  GITHUB_API_PATTERN,
  GITHUB_CORS_HEADERS,
  STUB_GITHUB_STARS,
  STUB_HEADER,
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

  test('the home page loads nothing from a third-party host', async ({
    context,
    page,
  }) => {
    await loginAdmin(context);
    const appOrigin = new URL(BASE_URL).origin;
    const unstubbed: string[] = [];
    page.on('requestfinished', async (req) => {
      const url = new URL(req.url());
      if (!url.protocol.startsWith('http') || url.origin === appOrigin) return;
      const resp = await req.response();
      if (!resp?.headers()[STUB_HEADER]) unstubbed.push(req.url());
    });
    page.on('requestfailed', (req) => {
      if (new URL(req.url()).origin !== appOrigin) unstubbed.push(req.url());
    });

    await page.goto('/');
    // Feature previews load as they scroll into view.
    const outlet = page.locator(
      '#outlet_root [data-slot="scroll-area-viewport"]',
    );
    for (const f of [0.25, 0.5, 0.75, 1]) {
      await outlet.evaluate(
        (el, frac) =>
          el.scrollTo(0, (el.scrollHeight - el.clientHeight) * frac),
        f,
      );
      await expect
        .poll(() =>
          page.evaluate(() =>
            Array.from(document.images).every(
              (img) => !img.getAttribute('src') || img.complete,
            ),
          ),
        )
        .toBe(true);
    }
    await page.waitForLoadState('networkidle');

    expect(unstubbed).toEqual([]);
  });
});
