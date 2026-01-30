import { Page, expect } from '@playwright/test';

/**
 * Demo-specific utilities for ensuring content is fully loaded before recording.
 * These help prevent capturing loading states in demo videos.
 */

export interface WaitForContentOptions {
  /** Timeout in milliseconds (default: 30000) */
  timeout?: number;
  /** Additional selectors that must be visible */
  requiredSelectors?: string[];
  /** Whether to wait for network idle (default: true) */
  waitForNetworkIdle?: boolean;
}

/**
 * Common loading indicator selectors to wait for disappearance.
 */
const LOADING_SELECTORS = [
  // Generic loading indicators
  '[data-loading="true"]',
  '[aria-busy="true"]',
  '.loading',
  '.spinner',
  '.skeleton',
  // Lucide/icon spinners
  '.animate-spin',
  '[class*="animate-spin"]',
  // Common loading components
  '[data-testid="loading"]',
  '[data-testid="spinner"]',
  '[data-testid="skeleton"]',
  // React Query loading states
  '[data-loading-state="loading"]',
];

/**
 * Wait for all loading indicators to disappear.
 */
export async function waitForLoadingComplete(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  // Wait for each loading indicator to disappear
  for (const selector of LOADING_SELECTORS) {
    try {
      // Check if any elements match the selector
      const count = await page.locator(selector).count();
      if (count > 0) {
        // Wait for them to disappear
        await page.locator(selector).first().waitFor({
          state: 'hidden',
          timeout: timeout / LOADING_SELECTORS.length,
        });
      }
    } catch {
      // Ignore timeout errors - element might not exist
    }
  }
}

/**
 * Wait for images within a container to load.
 */
export async function waitForImagesToLoad(
  page: Page,
  containerSelector: string = 'body',
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  await page.waitForFunction(
    ({ selector, timeoutMs }) => {
      const container = document.querySelector(selector);
      if (!container) return true;

      const images = container.querySelectorAll('img');
      const imagePromises = Array.from(images).map((img) => {
        if (img.complete) return true;
        return new Promise((resolve) => {
          img.onload = () => resolve(true);
          img.onerror = () => resolve(true); // Don't block on failed images
          // Timeout for individual image
          setTimeout(() => resolve(true), timeoutMs / 2);
        });
      });

      return Promise.all(imagePromises).then(() => true);
    },
    { selector: containerSelector, timeoutMs: timeout },
    { timeout }
  );
}

/**
 * Wait for HeroDraft-specific content to load.
 * Handles different draft states - hero grid only shows in drafting/paused/completed states.
 */
export async function waitForHeroDraftReady(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  // Wait for loading indicators to disappear
  await waitForLoadingComplete(page, { timeout: timeout / 3 });

  // Wait for the modal to be visible
  const modal = page.locator('[data-testid="herodraft-modal"]');
  await modal.waitFor({ state: 'visible', timeout: timeout / 3 });

  // Check which state-specific content is visible
  // Hero grid only renders in drafting/paused/completed states
  const heroGrid = page.locator('[data-testid="herodraft-hero-grid"]');
  const waitingPhase = page.locator('[data-testid="herodraft-waiting-phase"]');
  const rollingPhase = page.locator('[data-testid="herodraft-rolling-phase"]');
  const choosingPhase = page.locator('[data-testid="herodraft-choosing-phase"]');

  // Wait for any of the main content areas to be visible
  await Promise.race([
    heroGrid.waitFor({ state: 'visible', timeout: timeout / 2 }).catch(() => {}),
    waitingPhase.waitFor({ state: 'visible', timeout: timeout / 2 }).catch(() => {}),
    rollingPhase.waitFor({ state: 'visible', timeout: timeout / 2 }).catch(() => {}),
    choosingPhase.waitFor({ state: 'visible', timeout: timeout / 2 }).catch(() => {}),
  ]);

  // If hero grid is visible, wait for heroes to load
  if (await heroGrid.isVisible()) {
    await waitForImagesToLoad(page, '[data-testid="herodraft-hero-grid"]', {
      timeout: timeout / 3,
    });

    // Wait for at least some heroes to be rendered
    await page.waitForFunction(
      () => {
        const grid = document.querySelector('[data-testid="herodraft-hero-grid"]');
        if (!grid) return false;
        const heroes = grid.querySelectorAll('[data-hero-id]');
        return heroes.length >= 10; // At least 10 heroes visible
      },
      { timeout: timeout / 3 }
    );
  }

  // Brief settle time for animations
  await page.waitForTimeout(300);
}

/**
 * Wait for Draft (Snake/Shuffle) content to load.
 */
export async function waitForDraftReady(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  // Wait for loading indicators to disappear
  await waitForLoadingComplete(page, { timeout: timeout / 2 });

  // Wait for draft modal or container
  const draftContainer = page.locator(
    '[data-testid="draft-modal"], [data-testid="draft-container"], .draft-view'
  );

  try {
    await draftContainer.first().waitFor({ state: 'visible', timeout: timeout / 2 });
  } catch {
    // Container might not exist yet
  }

  // Wait for team cards to be visible
  const teamCards = page.locator('[data-testid*="team-"], .team-card');
  try {
    await teamCards.first().waitFor({ state: 'visible', timeout: timeout / 4 });
  } catch {
    // Team cards might not exist
  }

  // Brief settle time
  await page.waitForTimeout(200);
}

/**
 * Wait for Bracket content to load.
 */
export async function waitForBracketReady(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  // Wait for loading indicators to disappear
  await waitForLoadingComplete(page, { timeout: timeout / 2 });

  // Wait for bracket container
  const bracketContainer = page.locator(
    '[data-testid="bracket"], .bracket-container, .bracket-view'
  );

  try {
    await bracketContainer.first().waitFor({ state: 'visible', timeout: timeout / 2 });
  } catch {
    // Container might not exist
  }

  // Brief settle time
  await page.waitForTimeout(200);
}

/**
 * Comprehensive wait for any page to be fully loaded and ready for demo recording.
 * Combines multiple loading checks.
 */
export async function waitForDemoReady(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000, requiredSelectors = [], waitForNetworkIdle = true } = options;

  // Wait for document ready
  await page.waitForFunction(() => document.readyState === 'complete', { timeout });

  // Wait for network to settle (if enabled)
  if (waitForNetworkIdle) {
    try {
      await page.waitForLoadState('networkidle', { timeout: timeout / 3 });
    } catch {
      // Network might not settle, continue anyway
    }
  }

  // Wait for loading indicators to disappear
  await waitForLoadingComplete(page, { timeout: timeout / 3 });

  // Wait for any required selectors
  for (const selector of requiredSelectors) {
    await page.locator(selector).first().waitFor({ state: 'visible', timeout: timeout / 4 });
  }

  // Wait for images in viewport to load
  await waitForImagesToLoad(page, 'body', { timeout: timeout / 3 });

  // Final settle time for any animations
  await page.waitForTimeout(500);
}

/**
 * Wait specifically for match modal content to load.
 */
export async function waitForMatchModalReady(
  page: Page,
  options: WaitForContentOptions = {}
): Promise<void> {
  const { timeout = 30000 } = options;

  // Wait for match modal to be visible
  const matchModal = page.locator('[data-testid="match-modal"], [role="dialog"]');
  await matchModal.first().waitFor({ state: 'visible', timeout: timeout / 2 });

  // Wait for loading to complete
  await waitForLoadingComplete(page, { timeout: timeout / 2 });

  // Wait for Start Draft or similar action buttons
  const actionButtons = page.locator(
    'button:has-text("Start Draft"), button:has-text("View Draft"), button:has-text("Live Draft")'
  );

  try {
    await actionButtons.first().waitFor({ state: 'visible', timeout: timeout / 2 });
  } catch {
    // Button might not exist for this match state
  }

  // Settle time
  await page.waitForTimeout(300);
}
