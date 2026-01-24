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
    const testIdMap = {
      first_pick: 'herodraft-choice-first-pick',
      second_pick: 'herodraft-choice-second-pick',
      radiant: 'herodraft-choice-radiant',
      dire: 'herodraft-choice-dire',
    };
    await this.page.locator(`[data-testid="${testIdMap[choice]}"]`).click();
  }

  async selectLoserChoice(
    choice: 'first_pick' | 'second_pick' | 'radiant' | 'dire'
  ): Promise<void> {
    const testIdMap = {
      first_pick: 'herodraft-remaining-first-pick',
      second_pick: 'herodraft-remaining-second-pick',
      radiant: 'herodraft-remaining-radiant',
      dire: 'herodraft-remaining-dire',
    };
    await this.page.locator(`[data-testid="${testIdMap[choice]}"]`).click();
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
    console.log(`[clickHero] Clicking hero ${heroId} with JS click...`);
    // Use dispatchEvent to bypass viewport checks
    // Playwright's native click fails when element is in a nested scrollable container
    await heroButton.dispatchEvent('click');
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
   * Pick an available hero by ID, with confirmation.
   */
  async pickHero(heroId: number): Promise<void> {
    console.log(`[pickHero] Attempting to pick hero ${heroId}...`);

    // Check if hero button is enabled before trying to click
    const heroButton = this.page.locator(`[data-testid="herodraft-hero-${heroId}"]`);
    const isDisabled = await heroButton.isDisabled().catch(() => true);
    console.log(`[pickHero] Hero ${heroId} disabled: ${isDisabled}`);

    if (isDisabled) {
      // Log the current draft state for debugging
      const currentAction = await this.page.locator('[data-testid="herodraft-current-action"]').textContent().catch(() => 'unknown');
      const teamAPicking = await this.isTeamAPicking();
      const teamBPicking = await this.isTeamBPicking();
      console.log(`[pickHero] Current action: ${currentAction}, Team A picking: ${teamAPicking}, Team B picking: ${teamBPicking}`);
      throw new Error(`Hero ${heroId} is disabled - cannot pick. Current action: ${currentAction}, Team A picking: ${teamAPicking}, Team B picking: ${teamBPicking}`);
    }

    await this.clickHero(heroId);
    console.log(`[pickHero] Clicked hero ${heroId}, waiting for confirm dialog...`);
    await this.assertConfirmDialogVisible();
    console.log(`[pickHero] Confirm dialog visible, confirming...`);
    await this.confirmHeroSelection();
    console.log(`[pickHero] Confirmed, waiting for draft update...`);
    await this.waitForDraftUpdate();
    console.log(`[pickHero] Hero ${heroId} pick complete!`);
  }

  /**
   * Pick the first available hero.
   */
  async pickFirstAvailableHero(): Promise<number> {
    const availableHero = this.page
      .locator('[data-hero-available="true"]')
      .first();
    const heroId = await availableHero.getAttribute('data-hero-id');

    await availableHero.click();
    await this.assertConfirmDialogVisible();
    await this.confirmHeroSelection();
    await this.waitForDraftUpdate();

    return heroId ? parseInt(heroId) : 0;
  }
}
