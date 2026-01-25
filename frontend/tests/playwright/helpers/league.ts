import { Page, Locator, BrowserContext, expect } from '@playwright/test';

const API_URL = 'https://localhost/api';

/**
 * League data returned from the API.
 */
export interface LeagueData {
  pk: number;
  name: string;
  prize_pool?: string;
  description?: string;
  rules?: string;
  tournaments_count?: number;
  matches_count?: number;
  created_at?: string;
  updated_at?: string;
}

/**
 * Options for editing a league.
 */
export interface EditLeagueOptions {
  name?: string;
  prizePool?: string;
  description?: string;
  rules?: string;
}

/**
 * Tab names for league page navigation.
 */
export type LeagueTab = 'info' | 'tournaments' | 'matches';

/**
 * Page Object for League pages.
 *
 * Encapsulates all interactions with the league UI including:
 * - Navigation between league tabs (Info, Tournaments, Matches)
 * - Edit modal management
 * - League data display
 */
export class LeaguePage {
  readonly page: Page;

  // Main containers
  readonly leaguePage: Locator;
  readonly leagueHeader: Locator;
  readonly leagueTitle: Locator;

  // Tab navigation
  readonly infoTab: Locator;
  readonly tournamentsTab: Locator;
  readonly matchesTab: Locator;

  // Edit modal elements
  readonly editButton: Locator;
  readonly editModal: Locator;
  readonly nameInput: Locator;
  readonly prizeInput: Locator;
  readonly descriptionInput: Locator;
  readonly rulesInput: Locator;
  readonly submitButton: Locator;
  readonly cancelButton: Locator;

  // Matches tab elements
  readonly steamLinkedFilterButton: Locator;
  readonly matchCards: Locator;

  constructor(page: Page) {
    this.page = page;

    // Main containers
    this.leaguePage = page.locator('[data-testid="league-page"], main');
    this.leagueHeader = page.locator('h1');
    this.leagueTitle = page.locator('h1');

    // Tab navigation
    this.infoTab = page.locator('[data-testid="league-tab-info"]');
    this.tournamentsTab = page.locator('[data-testid="league-tab-tournaments"]');
    this.matchesTab = page.locator('[data-testid="league-tab-matches"]');

    // Edit modal elements
    this.editButton = page.locator('[data-testid="edit-league-button"]');
    this.editModal = page.locator('[data-testid="edit-league-modal"]');
    this.nameInput = page.locator('[data-testid="league-name-input"]');
    this.prizeInput = page.locator('[data-testid="league-prize-input"]');
    this.descriptionInput = page.locator('[data-testid="league-description-input"]');
    this.rulesInput = page.locator('[data-testid="league-rules-input"]');
    this.submitButton = page.locator('[data-testid="league-submit-button"]');
    this.cancelButton = page.locator('button:has-text("Cancel")');

    // Matches tab elements
    this.steamLinkedFilterButton = page.locator('button:has-text("Steam linked only")');
    this.matchCards = page.locator('[data-testid^="league-match-card"]');
  }

  // ============================================================================
  // Navigation
  // ============================================================================

  /**
   * Navigate to a league page.
   *
   * @param leaguePk - League primary key
   * @param tab - Optional tab to navigate to ('info' | 'tournaments' | 'matches')
   */
  async goto(leaguePk: number, tab?: LeagueTab): Promise<void> {
    const path = tab ? `/leagues/${leaguePk}/${tab}` : `/leagues/${leaguePk}`;
    await this.page.goto(path);
    await this.waitForPageLoad();
  }

  /**
   * Wait for the league page to load.
   */
  async waitForPageLoad(): Promise<void> {
    await this.page.locator('body').waitFor({ state: 'visible' });
    await this.page.waitForLoadState('domcontentloaded');
    // Wait for league title to appear (indicates data is loaded)
    await this.leagueTitle.waitFor({ state: 'visible', timeout: 30000 });
  }

  // ============================================================================
  // Tab Navigation
  // ============================================================================

  /**
   * Click on a league tab by name.
   *
   * @param tabName - The tab to click ('info' | 'tournaments' | 'matches')
   */
  async clickTab(tabName: LeagueTab): Promise<void> {
    const tabLocators: Record<LeagueTab, Locator> = {
      info: this.infoTab,
      tournaments: this.tournamentsTab,
      matches: this.matchesTab,
    };

    const tab = tabLocators[tabName];
    await tab.click();
    await this.waitForTabContent(tabName);
  }

  /**
   * Wait for tab content to be visible after clicking a tab.
   *
   * @param tabName - The tab that was clicked
   */
  private async waitForTabContent(tabName: LeagueTab): Promise<void> {
    // Wait for URL to update with the tab name
    await this.page.waitForURL(`**/${tabName}*`, { timeout: 10000 });
  }

  /**
   * Click the Info tab.
   */
  async clickInfoTab(): Promise<void> {
    await this.clickTab('info');
  }

  /**
   * Click the Tournaments tab.
   */
  async clickTournamentsTab(): Promise<void> {
    await this.clickTab('tournaments');
  }

  /**
   * Click the Matches tab.
   */
  async clickMatchesTab(): Promise<void> {
    await this.clickTab('matches');
  }

  // ============================================================================
  // Edit Modal
  // ============================================================================

  /**
   * Get the edit modal Locator.
   *
   * @returns Locator for the edit modal
   */
  getEditModal(): Locator {
    return this.editModal;
  }

  /**
   * Open the league edit modal.
   */
  async openEditModal(): Promise<void> {
    await this.editButton.waitFor({ state: 'visible' });
    await this.editButton.click();
    await this.editModal.waitFor({ state: 'visible' });
  }

  /**
   * Close the edit modal by clicking cancel.
   */
  async closeEditModal(): Promise<void> {
    await this.cancelButton.click();
    await this.editModal.waitFor({ state: 'hidden' });
  }

  /**
   * Close the edit modal by pressing Escape.
   */
  async closeEditModalWithEscape(): Promise<void> {
    await this.page.keyboard.press('Escape');
    await this.editModal.waitFor({ state: 'hidden' });
  }

  /**
   * Fill the edit form with provided values.
   *
   * @param options - Values to fill in the form
   */
  async fillEditForm(options: EditLeagueOptions): Promise<void> {
    if (options.name !== undefined) {
      await this.nameInput.clear();
      await this.nameInput.fill(options.name);
    }
    if (options.prizePool !== undefined) {
      await this.prizeInput.clear();
      await this.prizeInput.fill(options.prizePool);
    }
    if (options.description !== undefined) {
      await this.descriptionInput.clear();
      await this.descriptionInput.fill(options.description);
    }
    if (options.rules !== undefined) {
      await this.rulesInput.clear();
      await this.rulesInput.fill(options.rules);
    }
  }

  /**
   * Submit the edit form.
   */
  async submitEditForm(): Promise<void> {
    await this.submitButton.click();
  }

  /**
   * Edit a league with the provided values.
   *
   * @param options - Values to update
   */
  async editLeague(options: EditLeagueOptions): Promise<void> {
    await this.openEditModal();
    await this.fillEditForm(options);
    await this.submitEditForm();

    // Wait for success message
    await expect(
      this.page.locator('text=/updated successfully|success/i')
    ).toBeVisible({ timeout: 10000 });

    // Wait for modal to close
    await this.editModal.waitFor({ state: 'hidden' });
  }

  // ============================================================================
  // Matches Tab
  // ============================================================================

  /**
   * Toggle the Steam linked filter on the matches tab.
   */
  async toggleSteamLinkedFilter(): Promise<void> {
    await this.steamLinkedFilterButton.click();
  }

  /**
   * Check if the Steam linked filter is active.
   *
   * @returns true if the filter is active
   */
  async isSteamLinkedFilterActive(): Promise<boolean> {
    const classList = await this.steamLinkedFilterButton.getAttribute('class');
    return classList?.includes('bg-primary') ?? false;
  }

  /**
   * Get the count of match cards displayed.
   *
   * @returns Number of match cards visible
   */
  async getMatchCardCount(): Promise<number> {
    return this.matchCards.count();
  }

  // ============================================================================
  // Assertions
  // ============================================================================

  /**
   * Assert that the league page is visible.
   */
  async assertPageVisible(): Promise<void> {
    await expect(this.leaguePage).toBeVisible();
    await expect(this.leagueTitle).toBeVisible();
  }

  /**
   * Assert that all tab elements are visible.
   */
  async assertTabsVisible(): Promise<void> {
    await expect(this.infoTab).toBeVisible();
    await expect(this.tournamentsTab).toBeVisible();
    await expect(this.matchesTab).toBeVisible();
  }

  /**
   * Assert that a specific tab is active.
   *
   * @param tabName - The tab to check
   */
  async assertTabActive(tabName: LeagueTab): Promise<void> {
    const tabLocators: Record<LeagueTab, Locator> = {
      info: this.infoTab,
      tournaments: this.tournamentsTab,
      matches: this.matchesTab,
    };

    await expect(tabLocators[tabName]).toHaveAttribute('data-state', 'active');
  }

  /**
   * Assert that the edit button is visible.
   */
  async assertEditButtonVisible(): Promise<void> {
    await expect(this.editButton).toBeVisible();
  }

  /**
   * Assert that the edit button is not visible.
   */
  async assertEditButtonNotVisible(): Promise<void> {
    await expect(this.editButton).not.toBeVisible();
  }

  /**
   * Assert that the edit modal is visible.
   */
  async assertEditModalVisible(): Promise<void> {
    await expect(this.editModal).toBeVisible();
  }

  /**
   * Assert that the edit modal is not visible.
   */
  async assertEditModalNotVisible(): Promise<void> {
    await expect(this.editModal).not.toBeVisible();
  }

  /**
   * Assert that the league name is displayed.
   *
   * @param name - Expected league name
   */
  async assertLeagueName(name: string): Promise<void> {
    await expect(this.page.locator(`text=${name}`)).toBeVisible();
  }

  /**
   * Assert that form labels are visible in the edit modal.
   */
  async assertFormLabelsVisible(): Promise<void> {
    await expect(this.page.locator('label:has-text("League Name")')).toBeVisible();
    await expect(this.page.locator('label:has-text("Prize Pool")')).toBeVisible();
    await expect(this.page.locator('label:has-text("Description")')).toBeVisible();
    await expect(this.page.locator('label:has-text("Rules")')).toBeVisible();
  }
}

// ============================================================================
// Standalone Functions
// ============================================================================

/**
 * Navigate to a league page.
 * Standalone function for use without the LeaguePage class.
 *
 * @param page - Playwright Page instance
 * @param leaguePk - League primary key
 * @param tab - Optional tab to navigate to
 */
export async function navigateToLeague(
  page: Page,
  leaguePk: number,
  tab?: LeagueTab
): Promise<void> {
  const path = tab ? `/leagues/${leaguePk}/${tab}` : `/leagues/${leaguePk}`;
  await page.goto(path);
  await page.locator('body').waitFor({ state: 'visible' });
  await page.waitForLoadState('networkidle');
}

/**
 * Click a league tab by name.
 * Standalone function for use without the LeaguePage class.
 *
 * @param page - Playwright Page instance
 * @param tabName - The tab to click
 */
export async function clickLeagueTab(page: Page, tabName: LeagueTab): Promise<void> {
  const tabTestIds: Record<LeagueTab, string> = {
    info: 'league-tab-info',
    tournaments: 'league-tab-tournaments',
    matches: 'league-tab-matches',
  };

  await page.locator(`[data-testid="${tabTestIds[tabName]}"]`).click();
  await page.waitForURL(`**/${tabName}*`, { timeout: 10000 });
}

/**
 * Get the league edit modal Locator.
 * Standalone function for use without the LeaguePage class.
 *
 * @param page - Playwright Page instance
 * @returns Locator for the edit modal
 */
export function getLeagueEditModal(page: Page): Locator {
  return page.locator('[data-testid="edit-league-modal"]');
}

/**
 * Open the league edit modal.
 * Standalone function for use without the LeaguePage class.
 *
 * @param page - Playwright Page instance
 */
export async function openLeagueEditModal(page: Page): Promise<void> {
  const editButton = page.locator('[data-testid="edit-league-button"]');
  await editButton.waitFor({ state: 'visible' });
  await editButton.click();
  await page.locator('[data-testid="edit-league-modal"]').waitFor({ state: 'visible' });
}

/**
 * Fetch league data by primary key.
 *
 * @param context - Playwright BrowserContext for making API requests
 * @param leaguePk - League primary key
 * @returns League data or null if not found
 */
export async function getLeagueByPk(
  context: BrowserContext,
  leaguePk: number
): Promise<LeagueData | null> {
  const response = await context.request.get(
    `${API_URL}/leagues/${leaguePk}/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  return response.json();
}

/**
 * Fetch the first available league from the database.
 * Used for tests that need any valid league ID without hardcoding.
 *
 * @param context - Playwright BrowserContext for making API requests
 * @returns First league data or null if no leagues exist
 */
export async function getFirstLeague(
  context: BrowserContext
): Promise<LeagueData | null> {
  const response = await context.request.get(
    `${API_URL}/leagues/`,
    { failOnStatusCode: false }
  );

  if (!response.ok()) {
    return null;
  }

  const leagues = await response.json();
  if (Array.isArray(leagues) && leagues.length > 0) {
    return leagues[0];
  }

  // Handle paginated response
  if (leagues.results && Array.isArray(leagues.results) && leagues.results.length > 0) {
    return leagues.results[0];
  }

  return null;
}
