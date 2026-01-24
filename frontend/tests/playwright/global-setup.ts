import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  console.log('Global setup: Pre-fetching test data...');

  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  try {
    // Pre-fetch commonly used test data and store in env vars
    const leaguesResponse = await context.request.get('https://localhost/api/leagues/');
    if (leaguesResponse.ok()) {
      process.env.PLAYWRIGHT_CACHED_LEAGUES = JSON.stringify(await leaguesResponse.json());
    }
  } catch (error) {
    console.log('Global setup: Could not pre-fetch data, tests will fetch individually');
  }

  await browser.close();
}

export default globalSetup;
