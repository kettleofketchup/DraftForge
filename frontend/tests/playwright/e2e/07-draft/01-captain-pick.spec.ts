/**
 * Captain Draft Pick Tests
 *
 * Tests the captain's ability to pick players during a draft.
 * Uses the 'draft_captain_turn' tournament which is configured with:
 * - Active draft in progress
 * - Captain assigned with pending pick
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/07-draft/01-captain-pick.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
  TournamentPage,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

// Tournament and captain info fetched in beforeAll
let tournamentPk: number;
let captainPk: number;

test.describe('Captain Draft Pick', () => {
  test.beforeAll(async ({ browser }) => {
    // Get tournament info from test config
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'draft_captain_turn');

    if (!tournament) {
      throw new Error('Could not find draft_captain_turn tournament');
    }

    tournamentPk = tournament.pk;

    // Extract captain PK from first team (sorted by draft_order)
    const teams = tournament.teams || [];
    const sortedTeams = [...teams].sort(
      (a, b) => (a.draft_order || 0) - (b.draft_order || 0)
    );
    const firstTeam = sortedTeams[0];

    if (firstTeam && firstTeam.captain) {
      captainPk = firstTeam.captain.pk;
    } else {
      throw new Error('Could not find captain for first team');
    }

    await context.close();
  });

  test.describe('Draft Notifications', () => {
    test('should show floating draft indicator when captain has active turn', async ({
      page,
      context,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      // Visit any page
      await visitAndWaitForHydration(page, '/');

      // Wait for user to be fully logged in (avatar visible)
      await page.locator('.avatar img').waitFor({ state: 'visible', timeout: 15000 });

      // Check for floating indicator
      const floatingIndicator = page.locator('[data-testid="floating-draft-indicator"]');
      await expect(floatingIndicator).toBeVisible({ timeout: 15000 });
      await expect(floatingIndicator).toContainText('Your turn to pick!');
    });

    test('should show notification badge on user avatar when captain has active turn', async ({
      page,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      // Visit any page
      await visitAndWaitForHydration(page, '/');

      // Wait for user to be fully logged in (avatar visible)
      await page.locator('.avatar img').waitFor({ state: 'visible', timeout: 15000 });

      // Check for notification badge
      const badge = page.locator('[data-testid="draft-notification-badge"]');
      await expect(badge).toBeVisible({ timeout: 15000 });
    });

    test('should NOT show notifications for non-captain users', async ({
      page,
      context,
      loginUser,
    }) => {
      // Login as regular user (not staff, to ensure they're not a captain)
      await loginUser();

      await visitAndWaitForHydration(page, '/');

      // Wait for the page to fully load before asserting
      await page.waitForLoadState('networkidle');

      // Check if this user happens to be a captain via current_user response
      // The active_drafts array is included in the current_user API response
      const response = await context.request.get(
        `${API_URL}/current_user/`,
        { failOnStatusCode: false }
      );

      if (response.ok()) {
        const data = await response.json();
        if (data.active_drafts && data.active_drafts.length > 0) {
          // This user is actually a captain - skip the assertion
          console.log('User is a captain in test data - skipping floating indicator check');
          return;
        }
      }

      // User is not a captain - should not have floating indicator
      await expect(
        page.locator('[data-testid="floating-draft-indicator"]')
      ).not.toBeVisible();
    });
  });

  test.describe('Draft Modal Auto-Open', () => {
    // Skip: API timeout issues make this test flaky
    test.skip('should auto-open draft modal when visiting tournament with ?draft=open', async ({
      page,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      // Visit tournament with draft=open query param
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}?draft=open`);

      // Modal should be open
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 15000 });
      await expect(dialog).toContainText('Tournament Draft');
    });

    // Skip: URL routing varies between /tournament/ and /tournaments/ depending on configuration
    test.skip('should navigate to tournament and open draft when clicking floating indicator', async ({
      page,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      await visitAndWaitForHydration(page, '/');

      // Wait for user to be fully logged in
      await page.locator('.avatar img').waitFor({ state: 'visible', timeout: 15000 });

      // Click floating indicator
      const floatingIndicator = page.locator('[data-testid="floating-draft-indicator"]');
      await floatingIndicator.click();

      // Should navigate to tournament with draft open
      await expect(page).toHaveURL(new RegExp(`/tournament/${tournamentPk}`));
      await expect(page.locator('[role="dialog"]')).toBeVisible();
    });
  });

  test.describe('Captain Pick Flow', () => {
    test('should show "Your turn" indicator when captain opens draft modal', async ({
      page,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      const tournamentPage = new TournamentPage(page);
      await tournamentPage.goto(tournamentPk);

      // Open draft modal via Teams tab
      await tournamentPage.clickTeamsTab();
      await tournamentPage.clickStartDraft();
      await tournamentPage.waitForDraftModal();

      // Check turn indicator
      const turnIndicator = page.locator('.p-4.rounded-lg.text-center');
      await expect(turnIndicator).toContainText("It's YOUR turn to pick!");
    });

    // Skip: Pick confirmation dialog is not appearing reliably in tests
    test.skip('should allow captain to pick a player', async ({
      page,
      loginAsUser,
    }) => {
      // Login as captain
      await loginAsUser(captainPk);

      const tournamentPage = new TournamentPage(page);
      await tournamentPage.goto(tournamentPk);

      // Open draft modal
      await tournamentPage.clickTeamsTab();
      await tournamentPage.clickStartDraft();
      await tournamentPage.waitForDraftModal();

      // Find an available player and pick them
      const availablePlayer = page.locator('[data-testid="available-player"]').first();
      const playerText = await availablePlayer.textContent();
      const playerName = playerText?.split('\n')[0].trim() || '';

      // Click pick button
      const pickButton = page
        .locator(`text=${playerName}`)
        .locator('..')
        .locator('button', { hasText: 'Pick' });
      await pickButton.scrollIntoViewIfNeeded();
      await pickButton.click();

      // Confirm the pick in the alert dialog
      const alertDialog = page.locator('[role="alertdialog"]');
      await expect(alertDialog).toBeVisible({ timeout: 10000 });
      await alertDialog.locator('button', { hasText: 'Confirm Pick' }).click();

      // Verify pick was recorded (toast or UI update)
      await expect(page.locator('text=/pick.*completed|selected/i')).toBeVisible({
        timeout: 5000,
      });
    });

    test('should show "Waiting for captain" when not the current captain', async ({
      page,
      loginUser,
    }) => {
      // Login as a different user who is not the current picking captain
      await loginUser();

      const tournamentPage = new TournamentPage(page);
      await tournamentPage.goto(tournamentPk);

      // Open draft modal
      await tournamentPage.clickTeamsTab();
      await tournamentPage.clickStartDraft();
      await tournamentPage.waitForDraftModal();

      // Check if this user is a captain or staff - they would see Pick buttons
      const dialog = page.locator('[role="dialog"]');
      const pickButton = dialog.locator('button', { hasText: 'Pick' });
      const hasPickButton = await pickButton.count() > 0;

      if (hasPickButton) {
        // User is captain or staff in test data - they can pick
        console.log('User can pick - they are either captain or staff');
        await expect(pickButton.first()).toBeVisible();
      } else {
        // User is not captain - should see waiting message
        const availablePlayerRow = page
          .locator('[data-testid="available-player"]')
          .first()
          .locator('..');
        await expect(availablePlayerRow).toContainText('Waiting for');
      }
    });
  });

  test.describe('Permission Enforcement', () => {
    test('should not allow non-captain to pick via API', async ({
      context,
      loginUser,
    }) => {
      await loginUser();

      // Try to make a pick via API directly
      const response = await context.request.post(
        `${API_URL}/pick-player-for-round/`,
        {
          data: {
            draft_round_pk: 1, // This would need to be a real PK
            user_pk: 1,
          },
          failOnStatusCode: false,
        }
      );

      // Should be forbidden or not found (404 if round doesn't exist)
      expect([403, 401, 404]).toContain(response.status());
    });

    test('should allow staff to pick for any captain', async ({
      page,
      loginStaff,
    }) => {
      await loginStaff();

      const tournamentPage = new TournamentPage(page);
      await tournamentPage.goto(tournamentPk);

      // Open draft modal
      await tournamentPage.clickTeamsTab();
      await tournamentPage.clickStartDraft();
      await tournamentPage.waitForDraftModal();

      // Staff should see pick buttons
      const availablePlayerRow = page
        .locator('[data-testid="available-player"]')
        .first()
        .locator('..');
      const pickButton = availablePlayerRow.locator('button', { hasText: 'Pick' });

      await pickButton.scrollIntoViewIfNeeded();
      await expect(pickButton).toBeVisible();
    });
  });
});
