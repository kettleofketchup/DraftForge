/**
 * Tournament Page Tests
 *
 * Tests for the tournaments list page API integration and display.
 * Ported from Cypress: frontend/tests/cypress/e2e/03-tournaments/01-page.cy.ts
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';

test.describe('API Integration Tests', () => {
  test.beforeEach(async ({ page }) => {
    // No-op setup - tests handle their own navigation
  });

  test('should handle API requests for tournaments', async ({ page }) => {
    // Navigate to tournaments page
    await visitAndWaitForHydration(page, '/tournaments');

    // Wait for tournament data to load - the API returns a large payload
    // so we wait directly for the expected content with extended timeout
    await expect(page.locator('body')).toContainText('Partial Bracket Test', { timeout: 30000 });
  });
});
