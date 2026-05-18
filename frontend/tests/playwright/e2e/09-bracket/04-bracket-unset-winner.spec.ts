/**
 * Bracket Unset Winner Tests
 *
 * Covers the full lifecycle that was missed by the original suite:
 *
 *  1. Sanity (no save): set → Unset Winner button appears.
 *  2. Persistence: set → Save → reload → bracket card shows the winner
 *     check AND modal still offers Unset Winner.
 *  3. Unset across save boundary: set → Save → reload → click Unset → Save
 *     → reload → bracket card has no winner check, modal shows Set Winner
 *     buttons again.
 *  4. Stuck-state recovery (issue #235): force the prod scenario where
 *     ``status=completed`` but ``winning_team`` no longer matches either
 *     team in the slots. Unset Winner must still be visible and clicking
 *     it must unstick the row.
 *
 * Uses deterministic match selection via the
 * ``[data-bracket-type][data-round][data-position]`` attributes on each
 * ``bracket-match-node`` rather than iterating + reopening (the close-and-
 * re-click pattern was flaky against React Flow's pan/zoom).
 *
 * The bracket UI exposes ``data-testid="bracket-team-slot-{slot}"`` with
 * ``data-team-status`` of ``winner | loser | pending | empty`` and (when
 * isWinner+isCompleted) a nested ``bracket-winner-check-{slot}`` element —
 * the assertions hit those so a stuck row can't slip past.
 *
 * Uses the dedicated 'bracket_unset_winner' tournament: 4 teams in a
 * double-elimination bracket, all games pending. Winners R1 position 0
 * has Alpha vs Beta which we drive in every test.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
} from '../../fixtures';
import type { Page, Locator } from '@playwright/test';

// Tournament pk is captured per-test from the reset response. The reset
// endpoint DELETES + recreates the tournament so the pk changes; capturing
// once in beforeAll would 404 on every test after the first.
let tournamentPk = 0;

/** Winners R1 position 0 — Alpha vs Beta. Always pending after a reset. */
const TARGET_MATCH_SELECTOR =
  '[data-testid="bracket-match-node"][data-bracket-type="winners"][data-round="1"][data-position="0"]';

test.describe('Bracket Unset Winner (e2e)', () => {
  test.beforeEach(async ({ loginStaff, page }) => {
    await loginStaff();
    // Reset the dedicated tournament between tests so each one starts from
    // the populated baseline (all games pending). The endpoint returns the
    // freshly-created tournament — we re-bind tournamentPk from its body
    // because the delete-and-recreate gives it a new pk.
    const resetResp = await page.context().request.post(
      '/api/tests/reset-tournament/bracket_unset_winner/',
    );
    expect(resetResp.status()).toBe(200);
    const tournament = await resetResp.json();
    tournamentPk = tournament.pk;
  });

  async function loadBracket(page: Page): Promise<void> {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');
  }

  /** Click the target Winners R1 P0 node and return the open modal dialog. */
  async function openTargetModal(page: Page): Promise<Locator> {
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(node).toBeVisible({ timeout: 10000 });
    await node.click({ force: true });
    const dialog = page.locator('[data-testid="matchStatsModal"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    return dialog;
  }

  async function closeModal(page: Page): Promise<void> {
    // Use the dialog's explicit close button — Escape was flaky when focus
    // landed on something non-dismissable inside the modal, leaving the
    // backdrop overlaying the Save button so the next click timed out.
    const dialog = page.locator('[data-testid="matchStatsModal"]');
    await dialog.locator('[data-testid="dialog-close-button"]').click();
    await expect(dialog).toBeHidden({ timeout: 5000 });
  }

  /** Click Save and wait for the "Unsaved changes" indicator to disappear. */
  async function clickSaveAndWait(page: Page) {
    await page.locator('[data-testid="saveBracketButton"]').click();
    await expect(page.locator('text=Unsaved changes')).toBeHidden({ timeout: 10000 });
  }

  test('@cicd sanity: staff can set and unset bracket winner (in-memory)', async ({ page }) => {
    await loadBracket(page);

    const dialog = await openTargetModal(page);
    await dialog.locator('[data-testid="radiantWinsButton"]').click();

    // Unset Winner appears in the same modal session.
    await expect(dialog.locator('[data-testid="unsetWinnerButton"]')).toBeVisible({
      timeout: 5000,
    });

    await dialog.locator('[data-testid="unsetWinnerButton"]').click();

    // Set Winner buttons return.
    await expect(dialog.locator('[data-testid="radiantWinsButton"]')).toBeVisible({
      timeout: 5000,
    });
  });

  test('winner persists across Save + reload and bracket card shows the check', async ({
    page,
  }) => {
    await loadBracket(page);

    // Set radiant as winner.
    let dialog = await openTargetModal(page);
    await dialog.locator('[data-testid="radiantWinsButton"]').click();
    await closeModal(page);

    // Save + reload — the boundary the original test never crossed.
    await clickSaveAndWait(page);
    await page.reload();
    await loadBracket(page).catch(async () => {
      // visitAndWaitForHydration above already ran via loadBracket; if the
      // bracketContainer takes longer post-reload, give it the same wait
      // semantics. Empty catch so the original loadBracket assertion fires.
    });
    // Belt-and-suspenders: wait for the bracket again after reload.
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');

    // Bracket card must render the green check on radiant.
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(node.locator('[data-testid="bracket-winner-check-radiant"]')).toBeVisible();
    await expect(node.locator('[data-testid="bracket-team-slot-radiant"]')).toHaveAttribute(
      'data-team-status',
      'winner',
    );
    await expect(node.locator('[data-testid="bracket-team-slot-dire"]')).toHaveAttribute(
      'data-team-status',
      'loser',
    );

    // Modal must still let the admin reverse the decision.
    dialog = await openTargetModal(page);
    await expect(dialog.locator('[data-testid="unsetWinnerButton"]')).toBeVisible({
      timeout: 5000,
    });
  });

  test('unset clears the winner on the bracket card after Save + reload', async ({
    page,
  }) => {
    await loadBracket(page);

    // Set + Save so we have a real persisted winner to unset.
    let dialog = await openTargetModal(page);
    await dialog.locator('[data-testid="radiantWinsButton"]').click();
    await closeModal(page);
    await clickSaveAndWait(page);
    await page.reload();
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');

    // Unset → Save → reload.
    dialog = await openTargetModal(page);
    await dialog.locator('[data-testid="unsetWinnerButton"]').click();
    await closeModal(page);
    await clickSaveAndWait(page);
    await page.reload();
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');

    // Bracket card: no winner check on either side, both slots back to pending.
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(node.locator('[data-testid="bracket-winner-check-radiant"]')).toHaveCount(0);
    await expect(node.locator('[data-testid="bracket-winner-check-dire"]')).toHaveCount(0);
    await expect(node.locator('[data-testid="bracket-team-slot-radiant"]')).toHaveAttribute(
      'data-team-status',
      'pending',
    );

    // Modal: Set Winner buttons must be back.
    dialog = await openTargetModal(page);
    await expect(dialog.locator('[data-testid="radiantWinsButton"]')).toBeVisible({
      timeout: 5000,
    });
    await expect(dialog.locator('[data-testid="unsetWinnerButton"]')).toBeHidden();
  });

  test('stuck-state recovery: status=completed with mismatched winning_team can still be unset (issue #235)', async ({
    page,
  }) => {
    await loadBracket(page);

    // Read the target match's game pk off the rendered node.
    const node = page.locator(TARGET_MATCH_SELECTOR);
    const matchPkAttr = await node.getAttribute('data-game-pk');
    const matchPk = matchPkAttr ? Number(matchPkAttr) : NaN;
    expect(Number.isFinite(matchPk)).toBe(true);

    // Force the production stuck state via test endpoint: Game.status
    // becomes 'completed' but winning_team is a team that isn't currently
    // in either slot, so mapApiMatchToMatch can't derive match.winner. This
    // is exactly the prod state that hid the Unset Winner button before
    // PR #236.
    const forced = await page.context().request.post(
      '/api/tests/bracket/force-mismatched-winning-team/',
      { data: { game_id: matchPk } },
    );
    expect(forced.status()).toBe(200);
    const forcedBody = await forced.json();
    expect(forcedBody.winning_team_id).not.toBe(forcedBody.radiant_team_id);
    expect(forcedBody.winning_team_id).not.toBe(forcedBody.dire_team_id);

    await page.reload();
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');

    // Bracket card: neither team is marked as winner since the FK doesn't
    // resolve to either slot. (The defining trait of the stuck state.)
    await expect(node.locator('[data-testid="bracket-winner-check-radiant"]')).toHaveCount(0);
    await expect(node.locator('[data-testid="bracket-winner-check-dire"]')).toHaveCount(0);

    // Modal: PR #236 surfaces Unset Winner even when winner is undefined
    // (gate is now `status === 'completed' || match.winner`). Without the
    // fix this assertion fails — the regression we want CI to catch.
    const dialog = await openTargetModal(page);
    await expect(dialog.locator('[data-testid="unsetWinnerButton"]')).toBeVisible({
      timeout: 5000,
    });
    await expect(dialog.locator('[data-testid="radiantWinsButton"]')).toBeHidden();

    // Click Unset → Save → reload. The store's recovery path resets just
    // status (since there's no winner to clear from downstream slots), so
    // after save the row is back to pending with Set Winner buttons.
    await dialog.locator('[data-testid="unsetWinnerButton"]').click();
    await closeModal(page);
    await clickSaveAndWait(page);
    await page.reload();
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    await page.waitForLoadState('networkidle');

    const recoveredDialog = await openTargetModal(page);
    await expect(
      recoveredDialog.locator('[data-testid="radiantWinsButton"]'),
    ).toBeVisible({ timeout: 5000 });
  });
});
