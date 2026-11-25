/**
 * Bracket Unset Winner Tests
 *
 * Covers the full set and unset winner lifecycle:
 *
 * Setting or unsetting a winner in the modal persists that match result on
 * its own, with no bracket-wide Save.
 *
 *  1. Sanity: set → Unset Winner button appears → unset.
 *  2. Persistence: set → reload → bracket card shows the winner check, the
 *     winner and loser sit in their next games, and the modal still offers
 *     Unset Winner.
 *  3. Unset: set → reload → Unset → reload → bracket card has no winner
 *     check, downstream slots are cleared, modal shows Set Winner again.
 *  4. Stuck-state recovery: force the scenario where
 *     ``status=completed`` but ``winning_team`` no longer matches either
 *     team in the slots. Unset Winner must still be visible and clicking
 *     it must unstick the row.
 *  5. Steam unlink (issue #921): unlinking the (never-linked) target game
 *     leaves it pending and the bracket loadable.
 *
 * Uses deterministic match selection via the
 * ``[data-bracket-type][data-round][data-position]`` attributes on each
 * ``bracket-match-node`` rather than iterating + reopening (the close-and-
 * re-click pattern raced React Flow's pan/zoom).
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

import type { Locator, Page } from '@playwright/test';
import {
  clickAndPersistMatchResult,
  expect,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { getCsrfToken } from '../../fixtures/events';

// Tournament pk is captured per-test from the reset response. The reset
// endpoint DELETES + recreates the tournament so the pk changes; capturing
// once in beforeAll would 404 on every test after the first.
let tournamentPk = 0;

/** Winners R1 position 0 — Alpha vs Beta. Always pending after a reset. */
const TARGET_MATCH_SELECTOR =
  '[data-testid="bracket-match-node"][data-bracket-type="winners"][data-round="1"][data-position="0"]';

test.describe('Bracket Unset Winner (e2e)', () => {
  // Every test resets the same tournament and rebinds the module-scoped
  // tournamentPk; fullyParallel with PLAYWRIGHT_WORKERS=2 would race them.
  // Serial costs nothing at workers=1.
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ loginStaff, page }) => {
    await loginStaff();
    // Reset to the populated baseline (all games pending); the response
    // carries the recreated tournament's new pk.
    const resetResp = await page
      .context()
      .request.post('/api/tests/reset-tournament/bracket_unset_winner/');
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
    await node.click();
    const dialog = page.locator('[data-testid="matchStatsModal"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    return dialog;
  }

  async function closeModal(page: Page): Promise<void> {
    // Close via the button: Escape is ignored when focus sits on a
    // non-dismissable element, leaving the backdrop over Save and timing out
    // the next click.
    const dialog = page.locator('[data-testid="matchStatsModal"]');
    await dialog.locator('[data-testid="dialog-close-button"]').click();
    await expect(dialog).toBeHidden({ timeout: 5000 });
    // The dialog deep-links via /match/<id>; the next load must not reopen it.
    await expect(page).not.toHaveURL(/\/bracket\/match\//);
  }

  type ApiTeam = { pk: number } | null;
  type ApiGame = {
    pk: number;
    bracket_type: string;
    round: number;
    position: number;
    status: string;
    radiant_team: ApiTeam;
    dire_team: ApiTeam;
    next_game: number | null;
    next_game_slot: 'radiant' | 'dire' | null;
    loser_next_game: number | null;
    loser_next_game_slot: 'radiant' | 'dire' | null;
  };

  async function fetchGames(page: Page): Promise<ApiGame[]> {
    const resp = await page
      .context()
      .request.get(`/api/bracket/tournaments/${tournamentPk}/`);
    expect(resp.status()).toBe(200);
    return (await resp.json()).matches as ApiGame[];
  }

  async function fetchTargetGame(page: Page): Promise<ApiGame> {
    const game = (await fetchGames(page)).find(
      (g) => g.bracket_type === 'winners' && g.round === 1 && g.position === 0,
    );
    if (!game) throw new Error('winners R1 P0 game not found');
    return game;
  }

  function slotTeam(game: ApiGame, slot: 'radiant' | 'dire' | null): ApiTeam {
    return slot === 'radiant'
      ? game.radiant_team
      : slot === 'dire'
        ? game.dire_team
        : null;
  }

  test('@cicd sanity: staff can set and unset bracket winner from the modal', async ({
    page,
  }) => {
    await loadBracket(page);

    const dialog = await openTargetModal(page);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );

    // Unset Winner appears in the same modal session.
    await expect(
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    ).toBeVisible({
      timeout: 5000,
    });

    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    );

    // Set Winner buttons return.
    await expect(
      dialog.locator('[data-testid="radiantWinsButton"]'),
    ).toBeVisible({
      timeout: 5000,
    });
  });

  test('winner and loser advancement persist across reload without Save (issue #466)', async ({
    page,
  }) => {
    await loadBracket(page);

    // Set radiant as winner; the modal persists it, no bracket Save.
    let dialog = await openTargetModal(page);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );
    await closeModal(page);

    await loadBracket(page);

    // The server placed the winner in the next game and the loser in the
    // losers bracket.
    const games = await fetchGames(page);
    const source = games.find(
      (g) => g.bracket_type === 'winners' && g.round === 1 && g.position === 0,
    );
    expect(source).toBeDefined();
    const next = games.find((g) => g.pk === source!.next_game);
    const loserNext = games.find((g) => g.pk === source!.loser_next_game);
    expect(next).toBeDefined();
    expect(loserNext).toBeDefined();
    expect(slotTeam(next!, source!.next_game_slot)?.pk).toBe(
      source!.radiant_team?.pk,
    );
    expect(slotTeam(loserNext!, source!.loser_next_game_slot)?.pk).toBe(
      source!.dire_team?.pk,
    );

    // Bracket card must render the green check on radiant.
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(
      node.locator('[data-testid="bracket-winner-check-radiant"]'),
    ).toBeVisible();
    await expect(
      node.locator('[data-testid="bracket-team-slot-radiant"]'),
    ).toHaveAttribute('data-team-status', 'winner');
    await expect(
      node.locator('[data-testid="bracket-team-slot-dire"]'),
    ).toHaveAttribute('data-team-status', 'loser');

    // Modal must still let the admin reverse the decision.
    dialog = await openTargetModal(page);
    await expect(
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    ).toBeVisible({
      timeout: 5000,
    });
  });

  test('unset clears the winner on the bracket card after reload', async ({
    page,
  }) => {
    await loadBracket(page);

    // Persist a real winner to unset.
    let dialog = await openTargetModal(page);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );
    await closeModal(page);
    await loadBracket(page);

    dialog = await openTargetModal(page);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    );
    await closeModal(page);
    await loadBracket(page);

    // The advanced teams were pulled back out of the downstream slots.
    const games = await fetchGames(page);
    const source = games.find(
      (g) => g.bracket_type === 'winners' && g.round === 1 && g.position === 0,
    );
    const next = games.find((g) => g.pk === source!.next_game);
    const loserNext = games.find((g) => g.pk === source!.loser_next_game);
    expect(slotTeam(next!, source!.next_game_slot)).toBeNull();
    expect(slotTeam(loserNext!, source!.loser_next_game_slot)).toBeNull();

    // Bracket card: no winner check on either side, both slots back to pending.
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(
      node.locator('[data-testid="bracket-winner-check-radiant"]'),
    ).toHaveCount(0);
    await expect(
      node.locator('[data-testid="bracket-winner-check-dire"]'),
    ).toHaveCount(0);
    await expect(
      node.locator('[data-testid="bracket-team-slot-radiant"]'),
    ).toHaveAttribute('data-team-status', 'pending');

    // Modal: Set Winner buttons must be back.
    dialog = await openTargetModal(page);
    await expect(
      dialog.locator('[data-testid="radiantWinsButton"]'),
    ).toBeVisible({
      timeout: 5000,
    });
    await expect(
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    ).toBeHidden();
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
    const forced = await page
      .context()
      .request.post('/api/tests/bracket/force-mismatched-winning-team/', {
        data: { game_id: matchPk },
      });
    expect(forced.status()).toBe(200);
    const forcedBody = await forced.json();
    expect(forcedBody.winning_team_id).not.toBe(forcedBody.radiant_team_id);
    expect(forcedBody.winning_team_id).not.toBe(forcedBody.dire_team_id);

    await loadBracket(page);

    // Bracket card: neither team is marked as winner since the FK doesn't
    // resolve to either slot. (The defining trait of the stuck state.)
    await expect(
      node.locator('[data-testid="bracket-winner-check-radiant"]'),
    ).toHaveCount(0);
    await expect(
      node.locator('[data-testid="bracket-winner-check-dire"]'),
    ).toHaveCount(0);

    // Modal: PR #236 surfaces Unset Winner even when winner is undefined
    // (gate is now `status === 'completed' || match.winner`). Without the
    // fix this assertion fails — the regression we want CI to catch.
    const dialog = await openTargetModal(page);
    await expect(
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    ).toBeVisible({
      timeout: 5000,
    });
    await expect(
      dialog.locator('[data-testid="radiantWinsButton"]'),
    ).toBeHidden();

    // Click Unset → reload. There's no derivable winner to pull out of
    // downstream slots, so only the row resets: back to pending with Set
    // Winner buttons.
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="unsetWinnerButton"]'),
    );
    await closeModal(page);
    await loadBracket(page);

    const recoveredDialog = await openTargetModal(page);
    await expect(
      recoveredDialog.locator('[data-testid="radiantWinsButton"]'),
    ).toBeVisible({ timeout: 5000 });
  });

  test('@cicd unlinking a bracket game keeps the bracket loadable and the game pending (issue #921)', async ({
    page,
  }) => {
    const { pk: gamePk } = await fetchTargetGame(page);

    const unlinkResp = await page
      .context()
      .request.delete(`/api/steam/games/${gamePk}/unlink-match/`, {
        headers: { 'X-CSRFToken': await getCsrfToken(page.context()) },
      });
    expect(unlinkResp.status()).toBe(200);

    await loadBracket(page);
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(node).toBeVisible({ timeout: 10000 });
    await expect(node).toContainText('Upcoming');
    await expect(page.getByText('No bracket generated yet.')).toHaveCount(0);

    expect((await fetchTargetGame(page)).status).toBe('pending');
  });
});
