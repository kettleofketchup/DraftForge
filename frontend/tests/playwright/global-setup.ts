import { API_URL, BASE_URL } from './fixtures/base-url';
import { chromium } from '@playwright/test';
import type { FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  console.log('Global setup: Pre-fetching test data...');

  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  try {
    // Pre-fetch commonly used test data and store in env vars
    const leaguesResponse = await context.request.get(`${API_URL}/leagues/`);
    if (leaguesResponse.ok()) {
      process.env.PLAYWRIGHT_CACHED_LEAGUES = JSON.stringify(await leaguesResponse.json());
    }
  } catch (error) {
    console.log('Global setup: Could not pre-fetch data, tests will fetch individually');
  }

  // The test stack serves the Vite dev server, which transforms modules on first request.
  // Cold, the first tournament/draft page took 15-20 s on CI and timed out the first specs.
  try {
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/`, { waitUntil: 'load', timeout: 120_000 });
    const res = await context.request.get(`${API_URL}/tests/tournament-by-key/draft_captain_turn/`);
    if (res.ok()) {
      const { pk } = (await res.json()) as { pk: number };
      await page.goto(`${BASE_URL}/tournament/${pk}/teams/draft`, { waitUntil: 'load', timeout: 120_000 });
      await page.locator('[data-testid="tournamentDetailPage"]').waitFor({ timeout: 120_000 });
      await page.locator('[role="dialog"]').first().waitFor({ timeout: 120_000 });
    }
    console.log('Global setup: warmed the frontend dev server');
  } catch (error) {
    console.log(`Global setup: frontend warm-up failed: ${error}`);
  }

  await browser.close();
}

export default globalSetup;
