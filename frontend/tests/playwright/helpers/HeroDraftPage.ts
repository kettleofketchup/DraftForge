import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the HeroDraft (Captain's Mode) interface.
 *
 * Encapsulates all interactions with the draft UI including:
 * - Waiting phase (ready up)
 * - Rolling phase (coin flip)
 * - Choosing phase (pick order/side selection)
 * - Drafting phase (hero bans and picks)
 */
export class HeroDraftPage {
  readonly page: Page;

  // Main containers
  readonly modal: Locator;
  readonly topBar: Locator;
  readonly heroGrid: Locator;
  readonly draftPanel: Locator;

  // Phase indicators
  readonly waitingPhase: Locator;
  readonly rollingPhase: Locator;
  readonly choosingPhase: Locator;
  readonly mainArea: Locator;
  readonly pausedOverlay: Locator;

  // Buttons
  readonly readyButton: Locator;
  readonly flipCoinButton: Locator;
  readonly confirmSubmit: Locator;
  readonly confirmCancel: Locator;

  // Timers
  readonly graceTime: Locator;
  readonly teamAReserveTime: Locator;
  readonly teamBReserveTime: Locator;

  // Hero search
  readonly heroSearch: Locator;

  constructor(page: Page) {
    this.page = page;

    // Main containers
    this.modal = page.locator('[data-testid="herodraft-modal"]');
    this.topBar = page.locator('[data-testid="herodraft-topbar"]');
    this.heroGrid = page.locator('[data-testid="herodraft-hero-grid"]');
    this.draftPanel = page.locator('[data-testid="herodraft-panel"]');

    // Phase indicators
    this.waitingPhase = page.locator('[data-testid="herodraft-waiting-phase"]');
    this.rollingPhase = page.locator('[data-testid="herodraft-rolling-phase"]');
    this.choosingPhase = page.locator(
      '[data-testid="herodraft-choosing-phase"]'
    );
    this.mainArea = page.locator('[data-testid="herodraft-main-area"]');
    this.pausedOverlay = page.locator(
      '[data-testid="herodraft-paused-overlay"]'
    );

    // Buttons
    this.readyButton = page.locator('[data-testid="herodraft-ready-button"]');
    this.flipCoinButton = page.locator(
      '[data-testid="herodraft-flip-coin-button"]'
    );
    this.confirmSubmit = page.locator(
      '[data-testid="herodraft-confirm-submit"]'
    );
    this.confirmCancel = page.locator(
      '[data-testid="herodraft-confirm-cancel"]'
    );

    // Timers
    this.graceTime = page.locator('[data-testid="herodraft-grace-time"]');
    this.teamAReserveTime = page.locator(
      '[data-testid="herodraft-team-a-reserve-time"]'
    );
    this.teamBReserveTime = page.locator(
      '[data-testid="herodraft-team-b-reserve-time"]'
    );

    // Hero search
    this.heroSearch = page.locator('[data-testid="herodraft-hero-search"]');
  }

  // ============================================================================
  // Navigation
  // ============================================================================

  async goto(draftId: number): Promise<void> {
    await this.page.goto(`/herodraft/${draftId}`);
    await this.waitForModal();
  }

  async waitForModal(): Promise<void> {
    await this.modal.waitFor({ state: 'visible', timeout: 15000 });
  }

  // ============================================================================
  // Phase Assertions
  // ============================================================================

  async assertWaitingPhase(): Promise<void> {
    // Wait for any phase indicator to help debug
    try {
      await expect(this.waitingPhase).toBeVisible({ timeout: 10000 });
    } catch (e) {
      // Debug: check what phase we're actually in
      const phases = ['waiting', 'rolling', 'choosing', 'drafting', 'completed', 'abandoned'];
      for (const phase of phases) {
        const locator = this.page.locator(`[data-testid="herodraft-${phase}-phase"]`);
        if (await locator.isVisible().catch(() => false)) {
          throw new Error(`Expected waiting phase but found: ${phase}-phase`);
        }
      }
      // Check if modal is even visible
      const modalVisible = await this.modal.isVisible().catch(() => false);
      throw new Error(`Waiting phase not found. Modal visible: ${modalVisible}. Original error: ${e}`);
    }
  }

  async assertRollingPhase(): Promise<void> {
    await expect(this.rollingPhase).toBeVisible();
  }

  async assertChoosingPhase(): Promise<void> {
    await expect(this.choosingPhase).toBeVisible();
  }

  async assertDraftingPhase(): Promise<void> {
    await expect(this.mainArea).toBeVisible();
    await expect(
      this.page.locator('[data-testid="herodraft-hero-grid-container"]')
    ).toBeVisible();
  }

  async assertPaused(): Promise<void> {
    await expect(this.pausedOverlay).toBeVisible();
  }

  async assertConnected(): Promise<void> {
    await expect(
      this.page.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();
  }

  /**
   * Wait for WebSocket connection to be established.
   * Waits for the reconnecting indicator to disappear.
   */
  async waitForConnection(timeout = 10000): Promise<void> {
    // Wait for reconnecting indicator to disappear (means we're connected)
    await this.page
      .locator('[data-testid="herodraft-reconnecting"]')
      .waitFor({ state: 'hidden', timeout });
  }

  /**
   * Get current draft state from the page for debugging.
   */
  async getCurrentState(): Promise<string | null> {
    const phases = ['waiting', 'rolling', 'choosing', 'drafting', 'completed', 'abandoned', 'paused'];
    for (const phase of phases) {
      const locator = this.page.locator(`[data-testid="herodraft-${phase}-phase"]`);
      if (await locator.isVisible().catch(() => false)) {
        return phase;
      }
    }
    // Also check main-area for drafting/completed states
    if (await this.mainArea.isVisible().catch(() => false)) {
      return 'main-area-visible';
    }
    return null;
  }

  /**
   * Fetch draft state directly from API for debugging.
   */
  async fetchDraftStateFromAPI(draftId: number): Promise<{ state: string; teams: Array<{ is_ready: boolean; team_name: string }> } | null> {
    try {
      const response = await this.page.request.get(`https://localhost/api/herodraft/${draftId}/`, {
        failOnStatusCode: false,
      });
      if (response.ok()) {
        const data = await response.json();
        return {
          state: data.state,
          teams: data.draft_teams?.map((t: { is_ready: boolean; tournament_team: { name: string } }) => ({
            is_ready: t.is_ready,
            team_name: t.tournament_team?.name || 'unknown',
          })) || [],
        };
      }
    } catch (e) {
      console.error('Failed to fetch draft state from API:', e);
    }
    return null;
  }

  // ============================================================================
  // Waiting Phase Actions
  // ============================================================================

  async clickReady(): Promise<void> {
    // Wait for the ready button to be visible and enabled
    await this.readyButton.waitFor({ state: 'visible', timeout: 5000 });
    await expect(this.readyButton).toBeEnabled();
    await this.readyButton.click();
    // Wait for the button to disappear (indicates ready state was accepted)
    await this.readyButton.waitFor({ state: 'hidden', timeout: 5000 });
  }

  async assertCaptainReady(teamId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-ready-status-${teamId}"]`)
    ).toContainText('Ready');
  }

  async assertCaptainNotReady(teamId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-ready-status-${teamId}"]`)
    ).toContainText('Not Ready');
  }

  // ============================================================================
  // Rolling Phase Actions
  // ============================================================================

  async clickFlipCoin(): Promise<void> {
    await this.flipCoinButton.click();
  }

  // ============================================================================
  // Choosing Phase Actions
  // ============================================================================

  async selectWinnerChoice(
    choice: 'first_pick' | 'second_pick' | 'radiant' | 'dire'
  ): Promise<void> {
    console.log(`[selectWinnerChoice] Selecting ${choice}...`);
    const testIdMap = {
      first_pick: 'herodraft-choice-first-pick',
      second_pick: 'herodraft-choice-second-pick',
      radiant: 'herodraft-choice-radiant',
      dire: 'herodraft-choice-dire',
    };
    const choiceButton = this.page.locator(`[data-testid="${testIdMap[choice]}"]`);
    await choiceButton.waitFor({ state: 'visible', timeout: 10000 });
    await choiceButton.click();

    // Wait for confirm dialog to appear
    const confirmDialog = this.page.locator('[data-testid="herodraft-confirm-choice-dialog"]');
    await confirmDialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click confirm button
    const confirmButton = this.page.locator('[data-testid="herodraft-confirm-choice-submit"]');
    await confirmButton.waitFor({ state: 'visible', timeout: 3000 });
    await confirmButton.click();

    // Wait for dialog to close
    await confirmDialog.waitFor({ state: 'hidden', timeout: 10000 });
    console.log(`[selectWinnerChoice] Choice ${choice} confirmed!`);
  }

  async selectLoserChoice(
    choice: 'first_pick' | 'second_pick' | 'radiant' | 'dire'
  ): Promise<void> {
    console.log(`[selectLoserChoice] Selecting ${choice}...`);
    const testIdMap = {
      first_pick: 'herodraft-remaining-first-pick',
      second_pick: 'herodraft-remaining-second-pick',
      radiant: 'herodraft-remaining-radiant',
      dire: 'herodraft-remaining-dire',
    };

    // First wait for loser choices container to appear (depends on WebSocket update)
    const loserChoicesContainer = this.page.locator('[data-testid="herodraft-loser-choices"]');
    await loserChoicesContainer.waitFor({ state: 'visible', timeout: 15000 });

    const choiceButton = this.page.locator(`[data-testid="${testIdMap[choice]}"]`);
    await choiceButton.waitFor({ state: 'visible', timeout: 5000 });
    await choiceButton.click();

    // Wait for confirm dialog to appear
    const confirmDialog = this.page.locator('[data-testid="herodraft-confirm-choice-dialog"]');
    await confirmDialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click confirm button
    const confirmButton = this.page.locator('[data-testid="herodraft-confirm-choice-submit"]');
    await confirmButton.waitFor({ state: 'visible', timeout: 3000 });
    await confirmButton.click();

    // Wait for dialog to close
    await confirmDialog.waitFor({ state: 'hidden', timeout: 10000 });
    console.log(`[selectLoserChoice] Choice ${choice} confirmed!`);
  }

  async assertFlipWinner(): Promise<void> {
    await expect(
      this.page.locator('[data-testid="herodraft-flip-winner"]')
    ).toContainText('won the flip');
  }

  // ============================================================================
  // Drafting Phase Actions
  // ============================================================================

  async clickHero(heroId: number): Promise<void> {
    const heroButton = this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`);
    console.log(`[clickHero] Clicking hero ${heroId}...`);

    // Wait for button to be visible and not disabled
    await heroButton.waitFor({ state: 'visible', timeout: 5000 });

    // Double-check it's enabled right before clicking
    const isDisabledNow = await heroButton.isDisabled();
    if (isDisabledNow) {
      throw new Error(`Hero ${heroId} became disabled before click`);
    }

    // Scroll into view and use standard click (not force) to let Playwright handle actionability
    await heroButton.scrollIntoViewIfNeeded();

    // Small wait to let any pending state updates settle
    await this.page.waitForTimeout(100);

    // Click with standard behavior
    await heroButton.click();
    console.log(`[clickHero] Hero ${heroId} clicked!`);
  }

  async selectHeroByName(heroName: string): Promise<void> {
    await this.heroSearch.clear();
    await this.heroSearch.fill(heroName);
    await this.page.locator(`[data-hero-name="${heroName}"]`).click();
  }

  async confirmHeroSelection(): Promise<void> {
    await this.confirmSubmit.click();
  }

  async cancelHeroSelection(): Promise<void> {
    await this.confirmCancel.click();
  }

  async assertHeroAvailable(heroId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`)
    ).toHaveAttribute('data-hero-available', 'true');
  }

  async assertHeroUnavailable(heroId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`)
    ).toHaveAttribute('data-hero-available', 'false');
  }

  async assertHeroSelected(heroId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`)
    ).toHaveAttribute('data-hero-selected', 'true');
  }

  async assertConfirmDialogVisible(): Promise<void> {
    await expect(
      this.page.locator('[data-testid="herodraft-confirm-dialog"]')
    ).toBeVisible();
  }

  async assertConfirmDialogAction(action: 'pick' | 'ban'): Promise<void> {
    const expectedText = action === 'ban' ? 'Ban' : 'Pick';
    await expect(
      this.page.locator('[data-testid="herodraft-confirm-title"]')
    ).toContainText(expectedText);
  }

  // ============================================================================
  // Turn & Round Assertions
  // ============================================================================

  async assertMyTurn(): Promise<void> {
    await expect(this.topBar).toContainText('YOUR TURN');
  }

  async assertWaitingForOpponent(): Promise<void> {
    await expect(this.topBar).toContainText('PICKING');
  }

  async assertRoundActive(roundNumber: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-round-${roundNumber}"]`)
    ).toHaveAttribute('data-round-active', 'true');
  }

  async assertRoundCompleted(roundNumber: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-round-${roundNumber}"]`)
    ).toHaveAttribute('data-round-state', 'completed');
  }

  async assertRoundHeroId(roundNumber: number, heroId: number): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="herodraft-round-${roundNumber}-hero"]`)
    ).toHaveAttribute('data-hero-id', String(heroId));
  }

  async getCurrentRound(): Promise<number> {
    const activeRound = this.page.locator('[data-round-active="true"]');
    const testId = await activeRound.getAttribute('data-testid');
    const match = testId?.match(/herodraft-round-(\d+)/);
    return match ? parseInt(match[1]) : 0;
  }

  async getCurrentAction(): Promise<'pick' | 'ban'> {
    const actionText = await this.page
      .locator('[data-testid="herodraft-current-action"]')
      .textContent();
    return actionText?.toLowerCase().includes('ban') ? 'ban' : 'pick';
  }

  // ============================================================================
  // Timer Helpers
  // ============================================================================

  async getGraceTimeSeconds(): Promise<number> {
    const text = await this.graceTime.textContent();
    if (!text) return 0;
    const [mins, secs] = text.split(':').map(Number);
    return mins * 60 + secs;
  }

  async getTeamAReserveTimeSeconds(): Promise<number> {
    const text = await this.teamAReserveTime.textContent();
    if (!text) return 0;
    const [mins, secs] = text.split(':').map(Number);
    return mins * 60 + secs;
  }

  async getTeamBReserveTimeSeconds(): Promise<number> {
    const text = await this.teamBReserveTime.textContent();
    if (!text) return 0;
    const [mins, secs] = text.split(':').map(Number);
    return mins * 60 + secs;
  }

  /**
   * Check if Team A (left side of topbar) is currently picking.
   * Returns true if the "PICKING" indicator is visible for Team A.
   */
  async isTeamAPicking(): Promise<boolean> {
    const locator = this.page.locator('[data-testid="herodraft-team-a-picking"]');
    const isVisible = await locator.isVisible().catch(() => false);
    const count = await locator.count().catch(() => 0);
    if (!isVisible) {
      console.log(`[isTeamAPicking] Not visible. Element count: ${count}`);
    }
    return isVisible;
  }

  /**
   * Check if Team B (right side of topbar) is currently picking.
   * Returns true if the "PICKING" indicator is visible for Team B.
   */
  async isTeamBPicking(): Promise<boolean> {
    const locator = this.page.locator('[data-testid="herodraft-team-b-picking"]');
    const isVisible = await locator.isVisible().catch(() => false);
    const count = await locator.count().catch(() => 0);
    if (!isVisible) {
      console.log(`[isTeamBPicking] Not visible. Element count: ${count}`);
    }
    return isVisible;
  }

  // ============================================================================
  // Draft Completion
  // ============================================================================

  async assertDraftCompleted(): Promise<void> {
    // All rounds should be completed
    await expect(
      this.page.locator('[data-round-state="pending"]')
    ).not.toBeVisible();
    await expect(
      this.page.locator('[data-round-active="true"]')
    ).not.toBeVisible();
  }

  async assertAllHeroesDisabled(): Promise<void> {
    const heroButtons = this.page.locator(
      '[data-testid="herodraft-hero-grid"] button'
    );
    const count = await heroButtons.count();
    for (let i = 0; i < Math.min(count, 5); i++) {
      await expect(heroButtons.nth(i)).toBeDisabled();
    }
  }

  // ============================================================================
  // Utilities
  // ============================================================================

  async waitForDraftUpdate(timeout = 5000): Promise<void> {
    // Wait for WebSocket message to arrive and update UI
    await this.page.waitForTimeout(500);
  }

  async waitForPhaseTransition(
    targetPhase: 'waiting' | 'rolling' | 'choosing' | 'drafting' | 'completed',
    timeout = 10000
  ): Promise<void> {
    const phaseLocators = {
      waiting: this.waitingPhase,
      rolling: this.rollingPhase,
      choosing: this.choosingPhase,
      drafting: this.mainArea,
      completed: this.mainArea, // Completed also shows main area
    };

    await phaseLocators[targetPhase].waitFor({
      state: 'visible',
      timeout,
    });
  }

  /**
   * Wait for it to be the current user's turn to pick/ban.
   * Checks the data-hero-disabled attribute on hero buttons.
   */
  async waitForMyTurn(timeout = 10000): Promise<void> {
    console.log(`[waitForMyTurn] Waiting for turn...`);
    // Wait for any hero button to have data-hero-disabled="false"
    const enabledHero = this.page.locator('[data-hero-disabled="false"][data-hero-available="true"]').first();
    await enabledHero.waitFor({ state: 'visible', timeout });
    console.log(`[waitForMyTurn] Turn detected!`);
  }

  /**
   * Check if it's currently the user's turn to pick/ban.
   */
  async isMyTurn(): Promise<boolean> {
    // Check if any hero has data-hero-disabled="false" and data-hero-available="true"
    const enabledHero = this.page.locator('[data-hero-disabled="false"][data-hero-available="true"]').first();
    return enabledHero.isVisible().catch(() => false);
  }

  /**
   * Pick an available hero by ID, with confirmation.
   * Waits for the user's turn before attempting to pick.
   */
  async pickHero(heroId: number, options?: { waitForTurn?: boolean }): Promise<void> {
    const waitForTurn = options?.waitForTurn ?? true;
    console.log(`[pickHero] Attempting to pick hero ${heroId} (waitForTurn=${waitForTurn})...`);

    const heroButton = this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`);

    // Wait for hero button to exist
    await heroButton.waitFor({ state: 'visible', timeout: 5000 });

    // Check if hero is available
    const isAvailable = await heroButton.getAttribute('data-hero-available');
    if (isAvailable !== 'true') {
      throw new Error(`Hero ${heroId} is not available (already picked/banned)`);
    }

    // Optionally wait for it to be user's turn
    if (waitForTurn) {
      // Check if heroes are currently disabled (not user's turn)
      const isHeroDisabled = await heroButton.getAttribute('data-hero-disabled');
      if (isHeroDisabled === 'true') {
        console.log(`[pickHero] Waiting for turn (hero disabled)...`);
        await this.waitForMyTurn();
      }
    }

    // Double-check hero is still available after waiting
    const stillAvailable = await heroButton.getAttribute('data-hero-available');
    if (stillAvailable !== 'true') {
      throw new Error(`Hero ${heroId} became unavailable while waiting for turn`);
    }

    // Click the hero
    console.log(`[pickHero] Clicking hero ${heroId}...`);
    await heroButton.scrollIntoViewIfNeeded();
    await heroButton.click();

    // Wait for confirm dialog to appear
    console.log(`[pickHero] Waiting for confirm dialog...`);
    const confirmDialog = this.page.locator('[data-testid="herodraft-confirm-dialog"]');
    await confirmDialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click confirm button
    console.log(`[pickHero] Clicking confirm button...`);
    const confirmButton = this.page.locator('[data-testid="herodraft-confirm-submit"]');
    await confirmButton.waitFor({ state: 'visible', timeout: 3000 });
    await confirmButton.click();

    // Wait for dialog to close (indicates submission started)
    await confirmDialog.waitFor({ state: 'hidden', timeout: 10000 });
    console.log(`[pickHero] Hero ${heroId} pick submitted!`);

    // Wait for WebSocket update to propagate
    await this.waitForDraftUpdate();
    console.log(`[pickHero] Hero ${heroId} pick complete!`);
  }

  /**
   * Pick the first available hero.
   * Waits for the user's turn before attempting to pick.
   */
  async pickFirstAvailableHero(options?: { waitForTurn?: boolean }): Promise<number> {
    const waitForTurn = options?.waitForTurn ?? true;
    console.log(`[pickFirstAvailableHero] Finding first available hero (waitForTurn=${waitForTurn})...`);

    // Optionally wait for turn
    if (waitForTurn) {
      const isEnabled = await this.isMyTurn();
      if (!isEnabled) {
        console.log(`[pickFirstAvailableHero] Waiting for turn...`);
        await this.waitForMyTurn();
      }
    }

    // Find first hero that is available and not disabled
    const availableHero = this.page
      .locator('[data-hero-available="true"][data-hero-disabled="false"]')
      .first();

    await availableHero.waitFor({ state: 'visible', timeout: 5000 });
    const heroId = await availableHero.getAttribute('data-hero-id');
    const heroIdNum = heroId ? parseInt(heroId) : 0;

    console.log(`[pickFirstAvailableHero] Picking hero ${heroIdNum}...`);

    // Click the hero
    await availableHero.scrollIntoViewIfNeeded();
    await availableHero.click();

    // Wait for confirm dialog
    const confirmDialog = this.page.locator('[data-testid="herodraft-confirm-dialog"]');
    await confirmDialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click confirm
    const confirmButton = this.page.locator('[data-testid="herodraft-confirm-submit"]');
    await confirmButton.waitFor({ state: 'visible', timeout: 3000 });
    await confirmButton.click();

    // Wait for dialog to close
    await confirmDialog.waitFor({ state: 'hidden', timeout: 10000 });

    // Wait for WebSocket update
    await this.waitForDraftUpdate();
    console.log(`[pickFirstAvailableHero] Hero ${heroIdNum} pick complete!`);

    return heroIdNum;
  }

  /**
   * Ban a hero by ID, with confirmation.
   * This is an alias for pickHero since the same UI is used for both picks and bans.
   * The action type (pick vs ban) is determined by the current round type.
   */
  async banHero(heroId: number, options?: { waitForTurn?: boolean }): Promise<void> {
    console.log(`[banHero] Banning hero ${heroId}...`);
    await this.pickHero(heroId, options);
  }

  /**
   * Ban the first available hero.
   * This is an alias for pickFirstAvailableHero since the same UI is used for both.
   */
  async banFirstAvailableHero(options?: { waitForTurn?: boolean }): Promise<number> {
    console.log(`[banFirstAvailableHero] Banning first available hero...`);
    return this.pickFirstAvailableHero(options);
  }

  /**
   * Wait for the opponent to complete their pick/ban.
   * Waits for heroes to become disabled (not user's turn) then enabled again (user's turn).
   */
  async waitForOpponentPick(timeout = 30000): Promise<void> {
    console.log(`[waitForOpponentPick] Waiting for opponent to pick...`);

    // First wait for heroes to be disabled (opponent's turn started)
    const anyHero = this.page.locator('[data-hero-available="true"]').first();
    await anyHero.waitFor({ state: 'visible', timeout: 5000 });

    // Wait until it's our turn again
    await this.waitForMyTurn(timeout);
    console.log(`[waitForOpponentPick] Opponent pick complete, it's our turn!`);
  }

  /**
   * Wait for the draft to reach a specific phase.
   */
  async waitForDraftPhase(phase: 'waiting' | 'rolling' | 'choosing' | 'drafting' | 'completed', timeout = 30000): Promise<void> {
    console.log(`[waitForDraftPhase] Waiting for ${phase} phase...`);
    await this.waitForPhaseTransition(phase, timeout);
    console.log(`[waitForDraftPhase] Reached ${phase} phase!`);
  }
}
