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

    // Wait for page data to load before interacting with create button
    const createButton = page.getByRole('button', { name: /create tournament/i });
    await createButton.waitFor({ state: 'visible', timeout: 30000 });
    await createButton.click();

    // Fill the form fields
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });
    await nameInput.clear();
    await nameInput.fill(thisName);

    // Select a tournament type using data-testid
    const typeSelect = page.locator('[data-testid="tournament-type-select"]');
    await typeSelect.waitFor({ state: 'visible', timeout: 10000 });
    await typeSelect.click();

    // Wait for dropdown to open and select Single Elimination option
    const typeOption = page.locator('[data-testid="tournament-type-single"]');
    await typeOption.waitFor({ state: 'visible', timeout: 10000 });
    await typeOption.click();

    // Click the date picker button to open calendar popover
    const datePicker = page.locator('[data-testid="tournament-date-picker"]');
    await datePicker.waitFor({ state: 'visible', timeout: 10000 });
    await datePicker.click();

    // Wait for calendar popover to open
    const calendar = page.locator('[data-slot="calendar"]');
    await calendar.waitFor({ state: 'visible', timeout: 5000 });

    // Select day 15 of the current month (avoids outside days from previous/next month)
    // Find day button by matching exact text "15" within the calendar
    const dayButton = calendar.locator('button').filter({ hasText: /^15$/ }).first();
    // Use evaluate to bypass any popover positioning/z-index issues
    await dayButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    // Wait for popover to close
    await calendar.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});

    // Submit the form
    await page.locator('[data-testid="tournament-submit-button"]').click();

    // After submission, the created tournament should appear in the list.
    // Wait for success toast or navigation
    await page.waitForLoadState('networkidle');

    // Wait up to 15s for backend work and UI update
    // Use card-title to avoid matching the success toast, .first() to handle duplicates from reruns
    const createdTournament = page.locator('[data-slot="card-title"]').filter({ hasText: thisName }).first();
    await createdTournament.scrollIntoViewIfNeeded();
    await expect(createdTournament).toBeVisible({ timeout: 15000 });
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
    // Wait for tournament data to load (API returns large payload)
    await expect(page.getByText(completedBracketTest)).toBeVisible({ timeout: 30000 });

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
