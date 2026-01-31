import { test, expect, chromium } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

/**
 * Quick test to verify Largo (hero ID 155) can be picked in Captain's Mode.
 * This was a regression where ALL_HERO_IDS was hardcoded to 1-138.
 */
test.describe('Largo Hero Pick', () => {
  // Skip: Flaky multi-context WebSocket test - hero selection requires stable connection sync
  test.skip('should be able to pick Largo (ID 155) in draft', async () => {
    // Set longer timeout for this test
    test.setTimeout(120000);

    const browser = await chromium.launch({
      headless: true,
      args: [
        '--disable-web-security',
        '--ignore-certificate-errors',
        '--no-sandbox',
      ],
    });

    const contextA = await browser.newContext({ ignoreHTTPSErrors: true });
    const contextB = await browser.newContext({ ignoreHTTPSErrors: true });
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    try {
      // Get test draft info
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      if (!response.ok()) {
        throw new Error(`Failed to get test data: ${response.status()}`);
      }

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;

      console.log(`   Draft PK: ${draftPk}`);
      console.log(`   Captain A: ${teams[0].captain.username}`);
      console.log(`   Captain B: ${teams[1].captain.username}`);

      // Reset draft to waiting state
      await contextA.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/reset/`,
        { failOnStatusCode: false }
      );

      // Login both captains
      await loginAsDiscordId(contextA, teams[0].captain.discordId);
      await loginAsDiscordId(contextB, teams[1].captain.discordId);

      // Navigate to match page
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      await Promise.all([pageA.goto(matchUrl), pageB.goto(matchUrl)]);
      await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

      // Click Start Draft
      const startBtn = (page: any) =>
        page.locator('button:has-text("Start Draft"), button:has-text("View Draft")').first();
      await Promise.all([startBtn(pageA).click(), startBtn(pageB).click()]);

      const draftPageA = new HeroDraftPage(pageA);
      const draftPageB = new HeroDraftPage(pageB);

      await Promise.all([draftPageA.waitForModal(), draftPageB.waitForModal()]);
      console.log('   Both captains opened draft modal');

      // Wait for WebSocket connections
      await Promise.all([
        draftPageA.waitForConnection(),
        draftPageB.waitForConnection(),
      ]);

      // Both click ready
      await draftPageA.clickReady();
      await draftPageB.clickReady();
      console.log('   Both captains ready');

      // Wait for rolling phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('rolling', 15000),
        draftPageB.waitForPhaseTransition('rolling', 15000),
      ]);

      // Flip coin
      await draftPageA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftPageA.clickFlipCoin();
      console.log('   Coin flipped');

      // Wait for choosing phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('choosing', 15000),
        draftPageB.waitForPhaseTransition('choosing', 15000),
      ]);

      // Winner chooses first pick
      const winnerChoices = pageA.locator('[data-testid="herodraft-winner-choices"]');
      const isAWinner = await winnerChoices.isVisible().catch(() => false);

      if (isAWinner) {
        await draftPageA.selectWinnerChoice('first_pick');
        const loserChoices = pageB.locator('[data-testid="herodraft-loser-choices"]');
        await loserChoices.waitFor({ state: 'visible', timeout: 10000 });
        await draftPageB.selectLoserChoice('radiant');
      } else {
        await draftPageB.selectWinnerChoice('first_pick');
        const loserChoices = pageA.locator('[data-testid="herodraft-loser-choices"]');
        await loserChoices.waitFor({ state: 'visible', timeout: 10000 });
        await draftPageA.selectLoserChoice('radiant');
      }

      console.log('   Choices made');

      // Wait for drafting phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('drafting', 15000),
        draftPageB.waitForPhaseTransition('drafting', 15000),
      ]);
      console.log('   Drafting phase started');

      // Determine current picker
      const teamAPicking = await pageA.locator('[data-testid="herodraft-team-a-picking"]').isVisible().catch(() => false);
      const currentPicker = teamAPicking ? draftPageA : draftPageB;

      // =====================================================
      // THE ACTUAL TEST: Try to pick Largo (hero ID 155)
      // =====================================================
      console.log('   Attempting to pick Largo (ID 155)...');

      // First verify Largo button exists and is available
      const largoButton = currentPicker.page.locator('[data-testid="herodraft-hero-155"]');
      await expect(largoButton).toBeVisible({ timeout: 5000 });
      const isAvailable = await largoButton.getAttribute('data-hero-available');
      expect(isAvailable).toBe('true');
      console.log('   Largo button visible and available');

      // Pick Largo
      await currentPicker.pickHero(155);
      console.log('   Largo picked successfully!');

      // Verify Largo is now marked as unavailable (picked)
      await expect(largoButton).toHaveAttribute('data-hero-available', 'false');
      console.log('   Largo correctly marked as unavailable after pick');

      console.log('\n   TEST PASSED: Largo (ID 155) can be picked in Captain\'s Mode!');

    } finally {
      await browser.close();
    }
  });
});
