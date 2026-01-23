/**
 * Single Tournament Page Tests
 *
 * Tests for individual tournament page API integration and display.
 * Ported from Cypress: frontend/tests/cypress/e2e/04-tournament/01-page.cy.ts
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';

test.describe('API Integration Tests', () => {
  test.beforeEach(async () => {
    // No-op setup - tests handle their own navigation
  });

  test('should handle API requests for tournaments', async ({ page }) => {
    // Navigate to specific tournament page
    await visitAndWaitForHydration(page, '/tournament/1');

    // Verify the page displays the expected tournament data
    // "Completed Bracket Test" should be the tournament name
    await expect(page.locator('body')).toContainText('Completed Bracket Test');
  });
});
