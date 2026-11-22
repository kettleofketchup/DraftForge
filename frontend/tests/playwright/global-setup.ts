import type { FullConfig } from '@playwright/test';
import { chromium } from '@playwright/test';
import { API_URL, BASE_URL } from './fixtures/base-url';

async function globalSetup(config: FullConfig) {
  console.log('Global setup: Pre-fetching test data...');

  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  try {
    // Pre-fetch commonly used test data and store in env vars
    const leaguesResponse = await context.request.get(`${API_URL}/leagues/`);
    if (leaguesResponse.ok()) {
      process.env.PLAYWRIGHT_CACHED_LEAGUES = JSON.stringify(
        await leaguesResponse.json(),
      );
    }
  } catch (error) {
    console.log(
      'Global setup: Could not pre-fetch data, tests will fetch individually',
    );
  }

  // The test stack serves the Vite dev server, which transforms modules on first request.
  // Cold, the first tournament/draft page took 15-20 s on CI and timed out the first specs.
  const page = await context.newPage();
  page.on('console', (m) =>
    console.log(`[diag console.${m.type()}] ${m.text().slice(0, 800)}`),
  );
  page.on('pageerror', (e) => console.log(`[diag pageerror] ${e.stack}`));
  page.on('requestfailed', (r) =>
    console.log(`[diag requestfailed] ${r.url()} ${r.failure()?.errorText}`),
  );
  page.on('response', (r) => {
    if (r.status() >= 300 || r.url().includes('/api/'))
      console.log(`[diag response] ${r.status()} ${r.url()}`);
  });
  page.on('framenavigated', (f) => {
    if (f === page.mainFrame()) console.log(`[diag nav] ${f.url()}`);
  });
  try {
    await page.goto(`${BASE_URL}/`, { waitUntil: 'load', timeout: 120_000 });
    const res = await context.request.get(
      `${API_URL}/tests/tournament-by-key/draft_captain_turn/`,
    );
    if (res.ok()) {
      const { pk } = (await res.json()) as { pk: number };
      await page.goto(`${BASE_URL}/tournament/${pk}/teams/draft`, {
        waitUntil: 'load',
        timeout: 120_000,
      });
      await page
        .locator('[data-testid="tournamentDetailPage"]')
        .waitFor({ timeout: 120_000 });
      await page
        .locator('[role="dialog"]')
        .first()
        .waitFor({ timeout: 120_000 });
    }
    console.log('Global setup: warmed the frontend dev server');
  } catch (error) {
    console.log(`Global setup: frontend warm-up failed: ${error}`);
    console.log(`[diag url] ${page.url()}`);
    console.log(
      `[diag body] ${(await page.locator('body').innerText().catch(() => '')).slice(0, 3000)}`,
    );
    const html = await page.content().catch(() => '');
    console.log(`[diag html] ${html.slice(0, 6000)}`);
    await page
      .screenshot({ path: 'test-results/diag-warmup.png', fullPage: true })
      .catch(() => {});
  }

  await browser.close();
}

export default globalSetup;
