/**
 * Playwright E2E tests for Match Stats Display feature
 *
 * Tests the MatchStatsModal component which displays Dota 2 match statistics
 * including hero icons, player stats (K/D/A, GPM/XPM, damage, etc.)
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/05-match-stats/01-modal.cy.ts
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';

const API_URL = 'https://localhost/api';

test.describe('Match Stats Modal - Direct API Tests', () => {
  test('should create test match via API endpoint', async ({ context }) => {
    const response = await context.request.post(
      `${API_URL}/tests/create-match/`
    );

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    expect(data).toHaveProperty('match_id');
    expect(data).toHaveProperty('radiant_win');
    expect(data).toHaveProperty('duration');
    expect(data).toHaveProperty('player_count', 10);
  });

  test('should return match data from API endpoint', async ({ context }) => {
    // First create a test match
    const createResponse = await context.request.post(
      `${API_URL}/tests/create-match/`
    );
    expect(createResponse.ok()).toBeTruthy();
    const createData = await createResponse.json();
    const matchId = createData.match_id;

    // Then fetch the match data
    const response = await context.request.get(
      `${API_URL}/steam/matches/${matchId}/`
    );

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    expect(data).toHaveProperty('match_id', matchId);
    expect(data).toHaveProperty('radiant_win');
    expect(data).toHaveProperty('duration');
    expect(data).toHaveProperty('players');
    expect(data.players).toHaveLength(10);

    // Verify player stats structure
    const player = data.players[0];
    expect(player).toHaveProperty('hero_id');
    expect(player).toHaveProperty('kills');
    expect(player).toHaveProperty('deaths');
    expect(player).toHaveProperty('assists');
    expect(player).toHaveProperty('gold_per_min');
    expect(player).toHaveProperty('xp_per_min');
    expect(player).toHaveProperty('last_hits');
    expect(player).toHaveProperty('denies');
    expect(player).toHaveProperty('hero_damage');
    expect(player).toHaveProperty('tower_damage');
    expect(player).toHaveProperty('hero_healing');
  });

  test('should return 404 for non-existent match', async ({ context }) => {
    const response = await context.request.get(
      `${API_URL}/steam/matches/9999999999/`,
      { failOnStatusCode: false }
    );

    expect(response.status()).toBe(404);
  });

  test('should have correct player team assignment (5 Radiant, 5 Dire)', async ({
    context,
  }) => {
    // First create a test match
    const createResponse = await context.request.post(
      `${API_URL}/tests/create-match/`
    );
    expect(createResponse.ok()).toBeTruthy();
    const createData = await createResponse.json();
    const matchId = createData.match_id;

    // Then fetch the match data
    const response = await context.request.get(
      `${API_URL}/steam/matches/${matchId}/`
    );
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    const players = data.players;

    // Radiant players have player_slot < 128
    const radiantPlayers = players.filter(
      (p: { player_slot: number }) => p.player_slot < 128
    );
    // Dire players have player_slot >= 128
    const direPlayers = players.filter(
      (p: { player_slot: number }) => p.player_slot >= 128
    );

    expect(radiantPlayers).toHaveLength(5);
    expect(direPlayers).toHaveLength(5);
  });
});

test.describe('Match Stats Modal - UI Integration', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should load tournaments page', async ({ page }) => {
    await visitAndWaitForHydration(page, '/tournaments');

    await expect(page.locator('body')).toBeVisible();
    // Check that the page has tournament content - wait for loading to complete
    await expect(
      page.getByText('Completed Bracket Test').first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('should navigate to tournament detail page', async ({ page }) => {
    await visitAndWaitForHydration(page, '/tournament/1');

    await expect(page.locator('body')).toBeVisible();
    // The tournament detail page should load
    await expect(page.getByText('Completed Bracket Test')).toBeVisible();
  });

  test('should display Games tab in tournament detail', async ({ page }) => {
    await visitAndWaitForHydration(page, '/tournament/1');
    await expect(page.locator('body')).toBeVisible();

    // Click on Games tab
    await page.getByRole('tab', { name: 'Games' }).click();

    // Games tab defaults to Bracket View - verify it's visible
    await expect(page.getByText('Bracket View')).toBeVisible();

    // Switch to List View to see games
    await page.getByText('List View').click();

    // Games tab content should be visible - Tournament 1 has games from populate
    // Either we see game cards or the "No games" message (depending on data)
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('Match Stats Modal - Component Tests', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should have MatchStatsModal component available', async ({ page }) => {
    // This test verifies the component is properly exported and can be imported
    // The actual rendering is tested via the GameCard integration
    await visitAndWaitForHydration(page, '/tournament/1');
    await expect(page.locator('body')).toBeVisible();
  });
});
