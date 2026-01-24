import { test as base, expect, Browser, BrowserContext, Page } from '@playwright/test';
import { loginAsUser, waitForHydration, UserInfo } from './auth';

const API_URL = 'https://localhost/api';

/**
 * HeroDraft test fixtures that support two-captain scenarios.
 *
 * Creates two separate browser contexts (Captain A and Captain B)
 * that can be controlled independently during the test.
 */

export interface HeroDraftInfo {
  pk: number;
  state: string;
  draft_teams: Array<{
    id: number;
    captain: UserInfo;
    is_first_pick?: boolean;
    side?: 'radiant' | 'dire';
  }>;
  roll_winner?: {
    id: number;
    captain: UserInfo;
  };
  current_round?: number;
  grace_time_remaining?: number;
}

export interface CaptainContext {
  context: BrowserContext;
  page: Page;
  userInfo: UserInfo;
  teamId: number;
}

/**
 * Fetch HeroDraft info by test key.
 */
export async function getHeroDraftByKey(
  context: BrowserContext,
  key: string
): Promise<HeroDraftInfo | null> {
  const response = await context.request.get(
    `${API_URL}/tests/herodraft-by-key/${key}/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  return response.json();
}

/**
 * Reset a HeroDraft to its initial state.
 */
export async function resetHeroDraft(
  context: BrowserContext,
  draftId: number
): Promise<void> {
  await context.request.post(`${API_URL}/tests/herodraft/${draftId}/reset/`, {
    failOnStatusCode: false,
  });
}

/**
 * Create a new HeroDraft for testing with two captains.
 */
export async function createTestHeroDraft(
  context: BrowserContext
): Promise<HeroDraftInfo | null> {
  const response = await context.request.post(
    `${API_URL}/tests/herodraft/create/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  return response.json();
}

// Extended test fixture with two-captain support
export const test = base.extend<{
  // Two separate captain contexts
  captainA: CaptainContext;
  captainB: CaptainContext;

  // Draft info
  heroDraft: HeroDraftInfo;

  // Helper functions
  getHeroDraftByKey: (key: string) => Promise<HeroDraftInfo | null>;
  resetHeroDraft: (draftId: number) => Promise<void>;
}>({
  // Create Captain A context
  captainA: async ({ browser }, use) => {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    const page = await context.newPage();

    // Will be populated during test setup
    const captainContext: CaptainContext = {
      context,
      page,
      userInfo: { pk: 0, username: '' },
      teamId: 0,
    };

    await use(captainContext);

    // Cleanup
    await context.close();
  },

  // Create Captain B context (separate browser context)
  captainB: async ({ browser }, use) => {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    const page = await context.newPage();

    const captainContext: CaptainContext = {
      context,
      page,
      userInfo: { pk: 0, username: '' },
      teamId: 0,
    };

    await use(captainContext);

    // Cleanup
    await context.close();
  },

  // Get draft info - will be set during beforeEach
  heroDraft: async ({ captainA }, use) => {
    const draftInfo = await getHeroDraftByKey(
      captainA.context,
      'two_captain_test'
    );
    if (!draftInfo) {
      throw new Error('Could not fetch HeroDraft test data');
    }
    await use(draftInfo);
  },

  getHeroDraftByKey: async ({ captainA }, use) => {
    await use((key: string) => getHeroDraftByKey(captainA.context, key));
  },

  resetHeroDraft: async ({ captainA }, use) => {
    await use((draftId: number) => resetHeroDraft(captainA.context, draftId));
  },
});

export { expect } from '@playwright/test';

/**
 * Setup both captains for a HeroDraft test.
 * Logs in both captains and navigates them to the draft page.
 */
export async function setupTwoCaptains(
  captainA: CaptainContext,
  captainB: CaptainContext,
  draftInfo: HeroDraftInfo
): Promise<void> {
  const teams = draftInfo.draft_teams;
  if (teams.length < 2) {
    throw new Error('HeroDraft must have at least 2 teams');
  }

  // Login Captain A
  const captainAInfo = await loginAsUser(
    captainA.context,
    teams[0].captain.pk
  );
  captainA.userInfo = captainAInfo.user;
  captainA.teamId = teams[0].id;

  // Login Captain B
  const captainBInfo = await loginAsUser(
    captainB.context,
    teams[1].captain.pk
  );
  captainB.userInfo = captainBInfo.user;
  captainB.teamId = teams[1].id;

  // Navigate both to the draft page
  const draftUrl = `/herodraft/${draftInfo.pk}`;

  await Promise.all([
    captainA.page.goto(`https://localhost${draftUrl}`),
    captainB.page.goto(`https://localhost${draftUrl}`),
  ]);

  // Wait for both pages to hydrate
  await Promise.all([
    waitForHydration(captainA.page),
    waitForHydration(captainB.page),
  ]);
}

/**
 * Position browser windows side by side for visual debugging.
 */
export async function positionWindowsSideBySide(
  captainA: CaptainContext,
  captainB: CaptainContext
): Promise<void> {
  // Note: Window positioning requires CDP access
  // This is a placeholder - actual positioning depends on display setup
  console.log(
    'Tip: Manually arrange the two browser windows side by side for best viewing'
  );
}
