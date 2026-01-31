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

  test('Can edit a tournament via the form', async ({ page }) => {
    // Use existing test tournament - wait for it to load
    await expect(page.getByText(completedBracketTest)).toBeVisible({ timeout: 30000 });

    // Find the tournament card and click the Edit button
    const tournamentCard = page
      .getByText(completedBracketTest)
      .locator(
        'xpath=ancestor::*[contains(@class, "tournament-card") or contains(@class, "card") or self::article or self::li][1]'
      );

    // Open edit modal
    const editButton = tournamentCard.locator('button').filter({ hasText: /edit/i }).first();
    await editButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    // Wait for modal and name input
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });

    // Store original name for verification
    const originalName = await nameInput.inputValue();

    // Make a minor edit (add suffix)
    const editedNameWithSuffix = `${originalName} (edited)`;
    await nameInput.clear();
    await nameInput.fill(editedNameWithSuffix);

    // Find and click the save button
    const saveButton = page.getByRole('button', { name: /save changes/i }).first();
    await saveButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    // Wait for success message
    await expect(page.getByText(/successfully/i)).toBeVisible({ timeout: 10000 });

    // Verify edited name appears
    await expect(page.getByText(editedNameWithSuffix).first()).toBeVisible({ timeout: 10000 });

    // Revert the change to keep test data clean
    const editedCard = page
      .getByText(editedNameWithSuffix)
      .first()
      .locator(
        'xpath=ancestor::*[contains(@class, "tournament-card") or contains(@class, "card") or self::article or self::li][1]'
      );
    const revertEditButton = editedCard.locator('button').filter({ hasText: /edit/i }).first();
    await revertEditButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    const revertNameInput = page.locator('[data-testid="tournament-name-input"]');
    await revertNameInput.waitFor({ state: 'visible', timeout: 10000 });
    await revertNameInput.clear();
    await revertNameInput.fill(originalName);

    const revertSaveButton = page.getByRole('button', { name: /save changes/i }).first();
    await revertSaveButton.evaluate((btn) => (btn as HTMLButtonElement).click());
    await page.waitForLoadState('networkidle');
  });

  test('Can delete a tournament', async ({ page }) => {
    // First create a tournament to delete (so we don't destroy test data)
    const createButton = page.getByRole('button', { name: /create tournament/i });
    await createButton.waitFor({ state: 'visible', timeout: 30000 });
    await createButton.click();

    const deletableName = `Delete Test ${Date.now()}`;
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });
    await nameInput.fill(deletableName);

    // Select tournament type
    const typeSelect = page.locator('[data-testid="tournament-type-select"]');
    await typeSelect.click();
    const typeOption = page.locator('[data-testid="tournament-type-single"]');
    await typeOption.waitFor({ state: 'visible', timeout: 10000 });
    await typeOption.click();

    // Select date
    const datePicker = page.locator('[data-testid="tournament-date-picker"]');
    await datePicker.click();
    const calendar = page.locator('[data-slot="calendar"]');
    await calendar.waitFor({ state: 'visible', timeout: 5000 });
    const dayButton = calendar.locator('button').filter({ hasText: /^15$/ }).first();
    await dayButton.evaluate((btn) => (btn as HTMLButtonElement).click());
    await calendar.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});

    // Submit to create
    await page.locator('[data-testid="tournament-submit-button"]').click();
    await page.waitForLoadState('networkidle');

    // Verify it was created
    const createdTournament = page.locator('[data-slot="card-title"]').filter({ hasText: deletableName }).first();
    await createdTournament.scrollIntoViewIfNeeded();
    await expect(createdTournament).toBeVisible({ timeout: 15000 });

    // Find the tournament card - use the card structure: div.card contains the title
    // Cards use class "card card-compact" - find the one containing our tournament name
    const tournamentCard = page.locator('div.card').filter({ hasText: deletableName }).first();
    await tournamentCard.waitFor({ state: 'visible', timeout: 10000 });

    // Find the delete button - TrashIconButton uses variant="destructive" which applies bg-destructive
    // The button also has sr-only text "Delete" or "Delete tournament"
    const deleteButton = tournamentCard.getByRole('button', { name: /delete/i }).first();
    await deleteButton.waitFor({ state: 'visible', timeout: 10000 });
    await deleteButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    // Confirm deletion
    const confirmButton = page.getByRole('button', { name: 'Confirm Delete' });
    await confirmButton.waitFor({ state: 'visible', timeout: 5000 });
    await confirmButton.evaluate((btn) => (btn as HTMLButtonElement).click());

    // Wait for deletion success
    await expect(page.getByText(/deleted/i)).toBeVisible({ timeout: 10000 });

    // Verify tournament is gone
    await expect(page.locator('[data-slot="card-title"]').filter({ hasText: deletableName })).not.toBeVisible({ timeout: 5000 });
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
