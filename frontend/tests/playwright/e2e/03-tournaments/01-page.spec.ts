/**
 * Tournament Page Tests
 *
 * Tests for the tournaments list page API integration and display.
 * Ported from Cypress: frontend/tests/cypress/e2e/03-tournaments/01-page.cy.ts
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';
import { CARD_SELECTOR } from '../../helpers/tournament';

test.describe('API Integration Tests', () => {
  test('@cicd default tab lists upcoming tournaments and hides archived ones', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, '/tournaments');

    const panel = page.getByTestId('tournaments-panel-upcoming');
    await expect(panel).toHaveAttribute('data-fetching', 'false', { timeout: 30000 });

    const cardNamed = (name: string) =>
      page.locator(CARD_SELECTOR).filter({ hasText: name });

    await expect(cardNamed('Discovery Home Soon').first()).toBeVisible({ timeout: 30000 });
    await expect(cardNamed('Discovery Home Finished')).toHaveCount(0);
    await expect(cardNamed('Discovery Home Stale')).toHaveCount(0);
  });
});
