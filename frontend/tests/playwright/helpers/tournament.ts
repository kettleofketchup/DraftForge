import { Page, Locator, BrowserContext, expect } from '@playwright/test';

const API_URL = 'https://localhost/api';

/**
 * Tournament data returned from the test API endpoint.
 */
export interface TournamentData {
  pk: number;
  name: string;
  teams: Array<{
    pk: number;
    name: string;
    captain: {
      pk: number;
      username: string;
    };
    draft_order: number;
  }>;
  captains: Array<{
    pk: number;
    username: string;
  }>;
}

/**
 * Options for creating a tournament.
 */
export interface CreateTournamentOptions {
  name: string;
  tournamentType?: 'single_elimination' | 'double_elimination' | 'swiss';
  leaguePk?: number | null;
}

/**
 * Fetch tournament data by test configuration key.
 *
 * @param context - Playwright BrowserContext for making API requests
 * @param key - Test configuration key (e.g., 'completed_bracket', 'pending_bracket')
 * @returns Tournament data or null if not found
 */
export async function getTournamentByKey(
  context: BrowserContext,
  key: string
): Promise<TournamentData | null> {
  const response = await context.request.get(
    `${API_URL}/tests/tournament-by-key/${key}/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  return response.json();
}

/**
 * Page Object for Tournament pages.
 *
 * Encapsulates all interactions with tournament UI including:
 * - Navigation between tournament tabs (Players, Teams, Bracket)
 * - Player management (add/remove)
 * - Tournament creation
 * - Draft initiation
 */
export class TournamentPage {
  readonly page: Page;

  // Main containers
  readonly detailPage: Locator;
  readonly title: Locator;

  // Tab navigation
  readonly tabsList: Locator;
  readonly playersTab: Locator;
  readonly teamsTab: Locator;
  readonly bracketTab: Locator;

  // Tab content
  readonly playersTabContent: Locator;
  readonly teamsTabContent: Locator;
  readonly bracketTabContent: Locator;
  readonly bracketContainer: Locator;

  // Player management
  readonly addPlayerButton: Locator;
  readonly playerSearchInput: Locator;

  // Tournament creation
  readonly createButton: Locator;
  readonly createModal: Locator;
  readonly tournamentForm: Locator;
  readonly nameInput: Locator;
  readonly typeSelect: Locator;
  readonly datePicker: Locator;
  readonly leagueSelect: Locator;
  readonly submitButton: Locator;
  readonly cancelButton: Locator;

  // Draft buttons
  readonly startDraftButton: Locator;
  readonly liveDraftButton: Locator;
  readonly viewDraftButton: Locator;

  // Draft modal
  readonly draftModal: Locator;

  constructor(page: Page) {
    this.page = page;

    // Main containers
    this.detailPage = page.locator('[data-testid="tournamentDetailPage"]');
    this.title = page.locator('[data-testid="tournamentTitle"]');

    // Tab navigation
    this.tabsList = page.locator('[data-testid="tournamentTabsList"]');
    this.playersTab = page.locator('[data-testid="playersTab"]');
    this.teamsTab = page.locator('[data-testid="teamsTab"]');
    this.bracketTab = page.locator('[data-testid="bracketTab"]');

    // Tab content
    this.playersTabContent = page.locator('[data-testid="playersTabContent"]');
    this.teamsTabContent = page.locator('[data-testid="teamsTabContent"]');
    this.bracketTabContent = page.locator('[data-testid="bracketTabContent"]');
    this.bracketContainer = page.locator('[data-testid="bracketContainer"]');

    // Player management
    this.addPlayerButton = page.locator('[data-testid="tournamentAddPlayerBtn"]');
    this.playerSearchInput = page.locator('[data-testid="playerSearchInput"]');

    // Tournament creation
    this.createButton = page.locator('[data-testid="tournament-create-button"]');
    this.createModal = page.locator('[data-testid="tournament-create-modal"]');
    this.tournamentForm = page.locator('[data-testid="tournament-form"]');
    this.nameInput = page.locator('[data-testid="tournament-name-input"]');
    this.typeSelect = page.locator('[data-testid="tournament-type-select"]');
    this.datePicker = page.locator('[data-testid="tournament-date-picker"]');
    this.leagueSelect = page.locator('[data-testid="tournament-league-select"]');
    this.submitButton = page.locator('[data-testid="tournament-submit-button"]');
    this.cancelButton = page.locator('[data-testid="tournament-cancel-button"]');

    // Draft buttons - try multiple possible selectors
    this.startDraftButton = page.locator(
      'button:has-text("Start Draft"), [data-testid="startDraftButton"]'
    );
    this.liveDraftButton = page.locator(
      'button:has-text("Live Draft"), [data-testid="liveDraftButton"]'
    );
    this.viewDraftButton = page.locator(
      'button:has-text("View Draft"), [data-testid="viewDraftButton"]'
    );

    // Draft modal - HeroDraft modal or generic draft modal
    this.draftModal = page.locator(
      '[data-testid="herodraft-modal"], [data-testid="draftModal"], [role="dialog"]'
    );
  }

  // ============================================================================
  // Navigation
  // ============================================================================

  /**
   * Navigate to a tournament page.
   *
   * @param tournamentPk - Tournament primary key
   * @param tab - Optional tab to navigate to ('players' | 'teams' | 'games')
   */
  async goto(tournamentPk: number, tab?: 'players' | 'teams' | 'games'): Promise<void> {
    const path = tab ? `/tournament/${tournamentPk}/${tab}` : `/tournament/${tournamentPk}`;
    await this.page.goto(path);
    await this.waitForPageLoad();
  }

  /**
   * Wait for tournament page to load.
   */
  async waitForPageLoad(): Promise<void> {
    await this.detailPage.waitFor({ state: 'visible', timeout: 15000 });
  }

  /**
   * Navigate to tournament bracket/games tab.
   *
   * @param tournamentPk - Tournament primary key
   */
  async gotoGames(tournamentPk: number): Promise<void> {
    await this.goto(tournamentPk, 'games');
    await this.bracketContainer.waitFor({ state: 'visible', timeout: 15000 });
  }

  // ============================================================================
  // Tab Navigation
  // ============================================================================

  /**
   * Click the Players tab.
   */
  async clickPlayersTab(): Promise<void> {
    await this.playersTab.click();
    await this.playersTabContent.waitFor({ state: 'visible' });
  }

  /**
   * Click the Teams tab.
   */
  async clickTeamsTab(): Promise<void> {
    await this.teamsTab.click();
    await this.teamsTabContent.waitFor({ state: 'visible' });
  }

  /**
   * Click the Bracket tab.
   */
  async clickBracketTab(): Promise<void> {
    await this.bracketTab.click();
    await this.bracketContainer.waitFor({ state: 'visible', timeout: 15000 });
  }

  // ============================================================================
  // Draft Actions
  // ============================================================================

  /**
   * Click the Start Draft or Live Draft button.
   * Tries multiple button variations that may appear.
   */
  async clickStartDraft(): Promise<void> {
    // Try Start Draft first, then Live Draft, then View Draft
    const startVisible = await this.startDraftButton.isVisible().catch(() => false);
    if (startVisible) {
      await this.startDraftButton.click();
      return;
    }

    const liveVisible = await this.liveDraftButton.isVisible().catch(() => false);
    if (liveVisible) {
      await this.liveDraftButton.click();
      return;
    }

    const viewVisible = await this.viewDraftButton.isVisible().catch(() => false);
    if (viewVisible) {
      await this.viewDraftButton.click();
      return;
    }

    // Fallback: look for any button containing draft-related text
    const draftButton = this.page.locator(
      'button:has-text("Draft"), button:has-text("draft")'
    ).first();
    await draftButton.click();
  }

  /**
   * Wait for the draft modal to appear.
   *
   * @param timeout - Maximum time to wait (default: 15000ms)
   */
  async waitForDraftModal(timeout = 15000): Promise<void> {
    await this.draftModal.waitFor({ state: 'visible', timeout });
  }

  /**
   * Navigate to a specific draft via tournament bracket URL.
   *
   * @param tournamentPk - Tournament primary key
   * @param draftPk - Draft primary key
   */
  async gotoDraft(tournamentPk: number, draftPk: number): Promise<void> {
    await this.page.goto(`/tournament/${tournamentPk}/bracket/draft/${draftPk}`);
    await this.waitForDraftModal();
  }

  // ============================================================================
  // Player Management
  // ============================================================================

  /**
   * Open the add player dialog.
   */
  async openAddPlayerDialog(): Promise<void> {
    await this.addPlayerButton.scrollIntoViewIfNeeded();
    await this.addPlayerButton.click();
    await this.playerSearchInput.waitFor({ state: 'visible' });
  }

  /**
   * Add a player to the tournament.
   *
   * @param username - Player username to add
   */
  async addPlayer(username: string): Promise<void> {
    await this.openAddPlayerDialog();

    // Type username in search
    await this.playerSearchInput.fill(username);

    // Wait for and click the player option
    const playerOption = this.page.locator(`[data-testid="playerOption-${username}"]`);
    await playerOption.waitFor({ state: 'visible' });
    await playerOption.click();

    // Wait for success message
    await expect(
      this.page.locator('text=/added|created/i')
    ).toBeVisible({ timeout: 5000 });

    // Verify player card appears
    await this.page
      .locator(`[data-testid="usercard-${username}"]`)
      .waitFor({ state: 'visible' });
  }

  /**
   * Remove a player from the tournament.
   *
   * @param username - Player username to remove
   */
  async removePlayer(username: string): Promise<void> {
    const removeButton = this.page.locator(`[data-testid="removePlayerBtn-${username}"]`);
    await removeButton.scrollIntoViewIfNeeded();
    await removeButton.click();

    // Wait for success message
    await expect(
      this.page.locator('text=/removed|deleted/i')
    ).toBeVisible({ timeout: 5000 });

    // Verify player card is removed
    await expect(
      this.page.locator(`[data-testid="usercard-${username}"]`)
    ).not.toBeVisible();
  }

  /**
   * Get a player card element.
   *
   * @param username - Player username
   * @returns Locator for the player card
   */
  getPlayerCard(username: string): Locator {
    return this.page.locator(`[data-testid="usercard-${username}"]`);
  }

  // ============================================================================
  // Tournament Creation
  // ============================================================================

  /**
   * Open the create tournament modal.
   */
  async openCreateModal(): Promise<void> {
    await this.createButton.click();
    await this.createModal.waitFor({ state: 'visible' });
  }

  /**
   * Fill the tournament creation form.
   *
   * @param options - Tournament creation options
   */
  async fillForm(options: CreateTournamentOptions): Promise<void> {
    const { name, tournamentType = 'double_elimination', leaguePk } = options;

    // Fill tournament name
    await this.nameInput.clear();
    await this.nameInput.fill(name);

    // Select tournament type
    await this.typeSelect.click();
    const typeOption = this.page.locator(
      `[data-testid="tournament-type-${tournamentType.replace('_elimination', '')}"]`
    );
    await typeOption.waitFor({ state: 'visible' });
    await typeOption.click();

    // Select league if provided
    if (leaguePk !== undefined) {
      await this.leagueSelect.click();
      if (leaguePk === null) {
        await this.page
          .locator('[data-testid="tournament-league-none"]')
          .click();
      } else {
        await this.page
          .locator(`[data-testid="tournament-league-${leaguePk}"]`)
          .click();
      }
    }
  }

  /**
   * Submit the tournament creation form.
   */
  async submitForm(): Promise<void> {
    await this.submitButton.click();
  }

  /**
   * Create a new tournament.
   *
   * @param options - Tournament creation options
   */
  async createTournament(options: CreateTournamentOptions): Promise<void> {
    await this.openCreateModal();
    await this.fillForm(options);
    await this.submitForm();

    // Wait for success message
    await expect(
      this.page.locator('text=/created successfully/i')
    ).toBeVisible({ timeout: 5000 });
  }

  // ============================================================================
  // Assertions
  // ============================================================================

  /**
   * Assert that the tournament page is visible.
   */
  async assertPageVisible(): Promise<void> {
    await expect(this.detailPage).toBeVisible();
    await expect(this.title).toBeVisible();
  }

  /**
   * Assert that all tab elements are visible.
   */
  async assertTabsVisible(): Promise<void> {
    await expect(this.tabsList).toBeVisible();
    await expect(this.playersTab).toBeVisible();
    await expect(this.teamsTab).toBeVisible();
    await expect(this.bracketTab).toBeVisible();
  }

  /**
   * Assert that the Players tab content is visible.
   */
  async assertPlayersTabActive(): Promise<void> {
    await expect(this.playersTabContent).toBeVisible();
  }

  /**
   * Assert that the Teams tab content is visible.
   */
  async assertTeamsTabActive(): Promise<void> {
    await expect(this.teamsTabContent).toBeVisible();
  }

  /**
   * Assert that the Bracket tab content is visible.
   */
  async assertBracketTabActive(): Promise<void> {
    await expect(this.bracketContainer).toBeVisible();
  }

  /**
   * Assert that a player card is visible.
   *
   * @param username - Player username
   */
  async assertPlayerVisible(username: string): Promise<void> {
    await expect(this.getPlayerCard(username)).toBeVisible();
  }

  /**
   * Assert that a player card is not visible.
   *
   * @param username - Player username
   */
  async assertPlayerNotVisible(username: string): Promise<void> {
    await expect(this.getPlayerCard(username)).not.toBeVisible();
  }
}

/**
 * Navigate to a tournament page.
 * Standalone function for use without the TournamentPage class.
 *
 * @param page - Playwright Page instance
 * @param tournamentPk - Tournament primary key
 */
export async function navigateToTournament(
  page: Page,
  tournamentPk: number
): Promise<void> {
  await page.goto(`/tournament/${tournamentPk}`);
  await page.locator('[data-testid="tournamentDetailPage"]').waitFor({
    state: 'visible',
    timeout: 15000,
  });
}

/**
 * Click the Teams tab.
 * Standalone function for use without the TournamentPage class.
 *
 * @param page - Playwright Page instance
 */
export async function clickTeamsTab(page: Page): Promise<void> {
  await page.locator('[data-testid="teamsTab"]').click();
  await page.locator('[data-testid="teamsTabContent"]').waitFor({
    state: 'visible',
  });
}

/**
 * Click the Start Draft or Live Draft button.
 * Standalone function for use without the TournamentPage class.
 *
 * @param page - Playwright Page instance
 */
export async function clickStartDraft(page: Page): Promise<void> {
  const startButton = page.locator(
    'button:has-text("Start Draft"), [data-testid="startDraftButton"]'
  );
  const liveButton = page.locator(
    'button:has-text("Live Draft"), [data-testid="liveDraftButton"]'
  );
  const viewButton = page.locator(
    'button:has-text("View Draft"), [data-testid="viewDraftButton"]'
  );

  if (await startButton.isVisible().catch(() => false)) {
    await startButton.click();
  } else if (await liveButton.isVisible().catch(() => false)) {
    await liveButton.click();
  } else if (await viewButton.isVisible().catch(() => false)) {
    await viewButton.click();
  } else {
    // Fallback
    await page.locator('button:has-text("Draft")').first().click();
  }
}

/**
 * Wait for the draft modal to appear.
 * Standalone function for use without the TournamentPage class.
 *
 * @param page - Playwright Page instance
 * @param timeout - Maximum time to wait (default: 15000ms)
 */
export async function waitForDraftModal(
  page: Page,
  timeout = 15000
): Promise<void> {
  await page
    .locator(
      '[data-testid="herodraft-modal"], [data-testid="draftModal"], [role="dialog"]'
    )
    .waitFor({ state: 'visible', timeout });
}
