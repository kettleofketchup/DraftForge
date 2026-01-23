/**
 * League Page Edit Modal Tests
 *
 * Tests the edit modal functionality on league pages.
 * Verifies that admin users can edit leagues and form validation works.
 *
 * Uses the first available league from the database.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/10-leagues/02-edit-modal.cy.ts
 */

import {
  test,
  expect,
  LeaguePage,
  getFirstLeague,
} from '../../fixtures';

// Will be set dynamically in beforeAll
let testLeagueId: number;

// Edited name for testing the edit modal
const EDITED_LEAGUE_NAME = `Playwright Test League ${Date.now()}`;

// Test data for edit form
const TEST_PRIZE_POOL = '$5,000';
const TEST_DESCRIPTION = 'Updated description from Playwright test';

test.describe('League Page - Edit Modal (e2e)', () => {
  test.beforeAll(async ({ browser }) => {
    // Get the first available league dynamically
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const league = await getFirstLeague(context);
    if (!league) {
      throw new Error('No leagues found in database. Run inv db.populate.all first.');
    }
    testLeagueId = league.pk;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    // Login as admin to have edit permissions
    await loginAdmin();
  });

  test('should show edit button for admin users', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Edit button should be visible
    await leaguePage.assertEditButtonVisible();
    await expect(leaguePage.editButton).toContainText('Edit League');
  });

  test('should open edit modal when clicking edit button', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Click edit button
    await leaguePage.openEditModal();

    // Modal should be visible with correct elements
    await expect(page.locator('text=Edit League')).toBeVisible();
    await expect(leaguePage.nameInput).toBeVisible();
    await expect(leaguePage.prizeInput).toBeVisible();
    await expect(leaguePage.descriptionInput).toBeVisible();
    await expect(leaguePage.rulesInput).toBeVisible();
    await expect(leaguePage.submitButton).toBeVisible();
  });

  test('should close modal when clicking cancel', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Open modal
    await leaguePage.openEditModal();

    // Click cancel button
    await leaguePage.closeEditModal();

    // Modal should be closed
    await leaguePage.assertEditModalNotVisible();
  });

  test('should populate form with current league data', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Open modal
    await leaguePage.openEditModal();

    // Form should have current league data - name should not be empty
    const nameValue = await leaguePage.nameInput.inputValue();
    expect(nameValue).not.toBe('');
  });

  test('should validate required fields', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Open modal
    await leaguePage.openEditModal();

    // Clear name field (required)
    await leaguePage.nameInput.clear();

    // Submit
    await leaguePage.submitEditForm();

    // Should show error message
    await expect(page.locator('text=/required|name is required/i')).toBeVisible({ timeout: 5000 });
  });

  test('should update league successfully', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Open modal
    await leaguePage.openEditModal();

    // Fill form with new data
    await leaguePage.fillEditForm({
      name: EDITED_LEAGUE_NAME,
      prizePool: TEST_PRIZE_POOL,
      description: TEST_DESCRIPTION,
    });

    // Submit
    await leaguePage.submitEditForm();

    // Should show success message
    await expect(page.locator('text=/updated successfully|success/i')).toBeVisible({ timeout: 10000 });

    // Modal should close
    await leaguePage.assertEditModalNotVisible();

    // Page should show updated name
    await expect(page.locator(`text=${EDITED_LEAGUE_NAME}`)).toBeVisible({ timeout: 5000 });
  });

  test('should not show edit button for non-admin users', async ({ page, loginUser }) => {
    // Login as regular user
    await loginUser();

    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Edit button should not be visible
    await leaguePage.assertEditButtonNotVisible();
  });
});

test.describe('League Page - Edit Modal Accessibility (e2e)', () => {
  test.beforeEach(async ({ page, loginAdmin }) => {
    await loginAdmin();
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');
    await leaguePage.openEditModal();
  });

  test('should have proper form labels', async ({ page }) => {
    const leaguePage = new LeaguePage(page);

    // Check that form fields have associated labels
    await leaguePage.assertFormLabelsVisible();
  });

  test('should close modal with Escape key', async ({ page }) => {
    const leaguePage = new LeaguePage(page);

    // Press Escape key
    await leaguePage.closeEditModalWithEscape();

    // Modal should be closed
    await leaguePage.assertEditModalNotVisible();
  });
});
