/**
 * Tournament Form Tests
 *
 * Tests for tournament creation, editing, and deletion via the UI.
 * Ported from Cypress: frontend/tests/cypress/e2e/03-tournaments/02-form.cy.ts
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';
import { TournamentPage } from '../../helpers/tournament';

// Generate dynamic test data similar to Cypress constants
const getDateYYYYMMDD = (): string => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const getDate2YYYYMMDD = (): string => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 2).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const dateYYYYMMDD = getDateYYYYMMDD();
const date2YYYYMMDD = getDate2YYYYMMDD();
const thisName = `Playwright Tournament ${dateYYYYMMDD}`;
const editedName = `Playwright Tournament Edited ${date2YYYYMMDD}`;
const completedBracketTest = 'Completed Bracket Test';

test.describe('Tournaments - create (e2e)', () => {
  test.beforeEach(async ({ page, loginAdmin }) => {
    // Login as admin and navigate to tournaments page
    await loginAdmin();
    await visitAndWaitForHydration(page, '/tournaments');
  });

  test('logs in, creates a tournament via the UI and shows it in the list', async ({
    page,
  }) => {
    const tournamentPage = new TournamentPage(page);

    // Click the top-level Create Tournament button (opens the form/modal)
    await page.getByRole('button', { name: /create tournament/i }).click();

    // Fill the form fields
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });
    await nameInput.clear();
    await nameInput.fill(thisName);

    // Select a tournament type using the Shadcn Select trigger
    const typeLabel = page.getByText('Tournament Type');
    const typeParent = typeLabel.locator('..');
    const typeButton = typeParent.locator('button, [role="button"]').first();
    await typeButton.click();

    // Wait for dropdown to open and select Single Elimination option
    const typeOption = page
      .locator(
        '[role="option"], [data-radix-collection-item], .select-item, option'
      )
      .filter({ hasText: /single elimination/i })
      .first();
    await typeOption.waitFor({ state: 'visible', timeout: 10000 });
    await typeOption.click({ force: true });

    // Click the date picker button to open calendar popover
    const datePicker = page.locator('[data-testid="tournament-date-picker"]');
    await datePicker.waitFor({ state: 'visible', timeout: 10000 });
    await datePicker.click();

    // Select today's date from the calendar
    const dateCell = page.locator('[role="gridcell"]').filter({ hasText: /^\d+$/ }).first();
    await dateCell.click({ force: true });

    // Submit the form
    await page.locator('[data-testid="tournament-submit-button"]').click();

    // After submission, the created tournament should appear in the list.
    // Wait up to 10s for backend work and UI update.
    const createdTournament = page.getByText(thisName);
    await createdTournament.scrollIntoViewIfNeeded();
    await expect(createdTournament).toBeVisible({ timeout: 10000 });
  });

  // Skip: This test depends on the previous test's created tournament which may not persist
  test.skip('Can edit the form', async ({ page }) => {
    // Ensure the tournament exists
    await expect(page.getByText(thisName)).toBeVisible({ timeout: 10000 });

    // Find the tournament card and click the Edit button inside it
    const tournamentCard = page
      .getByText(thisName)
      .locator(
        'xpath=ancestor::*[contains(@class, "tournament-card") or contains(@class, "card") or self::article or self::li][1]'
      );

    await tournamentCard.locator('button').filter({ hasText: /edit/i }).first().click();

    // Clear and fill with edited name
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });
    await nameInput.clear();
    await nameInput.fill(editedName);

    // Find and click the save button
    await page.getByRole('button', { name: /save changes/i }).first().click();

    // Wait for success message
    await expect(page.getByText(/successfully/i)).toBeVisible({ timeout: 10000 });

    // Verify edited name appears
    const editedTournament = page.getByText(editedName);
    await editedTournament.scrollIntoViewIfNeeded();
    await expect(editedTournament).toBeVisible();
  });

  // Skip: This test depends on the previous test's edited tournament which may not persist
  test.skip('Can delete a tournament', async ({ page }) => {
    // Ensure the tournament exists
    const tournament = page.getByText(editedName);
    await expect(tournament).toBeVisible();
    await tournament.scrollIntoViewIfNeeded();

    // Find the tournament card and click the Delete button inside it
    const tournamentCard = tournament.locator(
      'xpath=ancestor::*[contains(@class, "tournament-card") or contains(@class, "card") or self::article or self::li][1]'
    );

    // Target the delete button by aria-label
    await tournamentCard.locator('[aria-label="Delete"]').click();

    // Click the confirmation delete button
    await page.getByRole('button', { name: 'Confirm Delete' }).click({ timeout: 10000 });

    // Wait for deletion success message
    await expect(
      page.getByText(/deleted|deleted successfully|removed/i)
    ).toBeVisible({ timeout: 2000 });
  });

  test('View Button works', async ({ page }) => {
    // Ensure the tournament exists
    await expect(page.getByText(completedBracketTest)).toBeVisible();

    // Find the tournament card and click the View button inside it
    const tournamentCard = page
      .getByText(completedBracketTest)
      .locator(
        'xpath=ancestor::*[contains(@class, "tournament-card") or contains(@class, "card") or self::article or self::li][1]'
      );

    // Click the View button
    await tournamentCard.getByRole('button', { name: 'View' }).click();

    // Verify URL changed to tournament detail page
    await expect(page).toHaveURL(/\/tournament\//);
  });
});
