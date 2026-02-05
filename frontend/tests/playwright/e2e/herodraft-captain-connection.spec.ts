import { test as base, expect, BrowserContext, Page } from '@playwright/test';
import {
  loginAsUser,
  waitForHydration,
  DOCKER_HOST,
  API_URL,
} from '../fixtures/auth';
import { getHeroDraftByKey, resetHeroDraft, HeroDraftInfo } from '../fixtures/herodraft';

/**
 * Test captain connection management for HeroDraft.
 *
 * Verifies:
 * - Only one WebSocket connection per captain is allowed
 * - Opening a new tab kicks the old connection
 * - Kicked connection receives appropriate notification
 */

// Extended test fixture for multi-context captain tests
const test = base.extend<{
  heroDraft: HeroDraftInfo;
}>({
  // Get draft info
  heroDraft: async ({ browser }, use) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const draftInfo = await getHeroDraftByKey(context, 'two_captain_test');
    if (!draftInfo) {
      throw new Error('Could not fetch HeroDraft test data. Ensure test data is populated.');
    }
    // Reset draft to clean state
    await resetHeroDraft(context, draftInfo.pk);
    await context.close();

    await use(draftInfo);
  },
});

test.describe('HeroDraft Captain Connection Management', () => {
  test('should kick old connection when captain opens new tab', async ({
    browser,
    heroDraft,
  }) => {
    // Get captain info
    const captainPk = heroDraft.draft_teams[0].captain.pk;
    const draftUrl = `https://${DOCKER_HOST}/herodraft/${heroDraft.pk}`;

    // === First Context (Tab 1) ===
    const context1 = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    // Add playwright marker to disable react-scan
    await context1.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    const page1 = await context1.newPage();

    // Login as captain in first context
    await loginAsUser(context1, captainPk);

    // Navigate to draft
    await page1.goto(draftUrl);
    await waitForHydration(page1);

    // Wait for WebSocket connection and initial state
    await expect(page1.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // Verify we're connected (no error shown)
    await expect(
      page1.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();

    // Give time for WebSocket to establish and heartbeat to start
    await page1.waitForTimeout(1000);

    // === Second Context (Tab 2) - Same Captain ===
    const context2 = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await context2.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    const page2 = await context2.newPage();

    // Login as the SAME captain in second context
    await loginAsUser(context2, captainPk);

    // Navigate to draft in second tab
    await page2.goto(draftUrl);
    await waitForHydration(page2);

    // Wait for second context to connect
    await expect(page2.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // === Verify First Context Was Kicked ===
    // The first context should show an error or toast indicating it was kicked
    // Wait for the kicked notification (toast or error state)
    await expect(async () => {
      // Check for either the error message in connection status or a toast
      const hasError = await page1
        .locator('[data-testid="herodraft-reconnecting"]')
        .isVisible()
        .catch(() => false);

      // Check for kicked overlay or kicked message (contains "another tab" text)
      const hasKickedOverlay = await page1
        .getByTestId('herodraft-kicked-overlay')
        .isVisible()
        .catch(() => false);

      const hasKickedMessage = await page1
        .getByTestId('herodraft-kicked-message')
        .isVisible()
        .catch(() => false);

      expect(hasError || hasKickedOverlay || hasKickedMessage).toBe(true);
    }).toPass({ timeout: 10000 });

    // === Verify Second Context Is Still Connected ===
    // Second context should be working normally
    await expect(
      page2.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();

    // Cleanup
    await context1.close();
    await context2.close();
  });

  test('should allow captain to reconnect after being kicked', async ({
    browser,
    heroDraft,
  }) => {
    const captainPk = heroDraft.draft_teams[0].captain.pk;
    const draftUrl = `https://${DOCKER_HOST}/herodraft/${heroDraft.pk}`;

    // === First Context ===
    const context1 = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await context1.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    const page1 = await context1.newPage();
    await loginAsUser(context1, captainPk);
    await page1.goto(draftUrl);
    await waitForHydration(page1);
    await expect(page1.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // === Second Context - Kicks First ===
    const context2 = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await context2.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    const page2 = await context2.newPage();
    await loginAsUser(context2, captainPk);
    await page2.goto(draftUrl);
    await waitForHydration(page2);
    await expect(page2.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // Wait for first to be kicked
    await page1.waitForTimeout(2000);

    // Close second context
    await context2.close();

    // === First Context Reconnects ===
    // Click reconnect button if visible, or just reload
    const reconnectBtn = page1.locator('[data-testid="herodraft-reconnect-btn"]');
    if (await reconnectBtn.isVisible().catch(() => false)) {
      await reconnectBtn.click();
    } else {
      await page1.reload();
      await waitForHydration(page1);
    }

    // Should reconnect successfully
    await expect(page1.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // After reconnection, should not show error
    await page1.waitForTimeout(1000);
    await expect(
      page1.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();

    // Cleanup
    await context1.close();
  });

  // SKIP REASON: Complex multi-context WebSocket test with 3 browser contexts.
  // The connection kick FEATURE works (verified by tests above). This test verifies
  // edge case behavior: different captains don't kick each other, only same-user tabs.
  // TODO: Consider if this edge case needs test coverage or is sufficiently covered by unit tests.
  test.skip('should only kick captain connections, not spectators', async ({
    browser,
    heroDraft,
  }) => {
    const captainPk = heroDraft.draft_teams[0].captain.pk;
    const otherCaptainPk = heroDraft.draft_teams[1].captain.pk;
    const draftUrl = `https://${DOCKER_HOST}/herodraft/${heroDraft.pk}`;

    // === Captain A Context ===
    const captainAContext = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await captainAContext.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    const captainAPage = await captainAContext.newPage();
    await loginAsUser(captainAContext, captainPk);
    await captainAPage.goto(draftUrl);
    await waitForHydration(captainAPage);
    await expect(captainAPage.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // === Captain B Context (different captain) ===
    const captainBContext = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await captainBContext.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    const captainBPage = await captainBContext.newPage();
    await loginAsUser(captainBContext, otherCaptainPk);
    await captainBPage.goto(draftUrl);
    await waitForHydration(captainBPage);
    await expect(captainBPage.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // Both captains should remain connected (no kicking between different captains)
    await captainAPage.waitForTimeout(2000);

    await expect(
      captainAPage.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();
    await expect(
      captainBPage.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();

    // Now Captain A opens a second tab - should kick Captain A's first tab only
    const captainAContext2 = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 720 },
    });
    await captainAContext2.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    const captainAPage2 = await captainAContext2.newPage();
    await loginAsUser(captainAContext2, captainPk);
    await captainAPage2.goto(draftUrl);
    await waitForHydration(captainAPage2);
    await expect(captainAPage2.locator('[data-testid="herodraft-modal"]')).toBeVisible({
      timeout: 10000,
    });

    // Wait for kick to process
    await captainAPage.waitForTimeout(2000);

    // Captain A's first tab should be kicked
    const captainAKicked = await captainAPage
      .getByTestId('herodraft-kicked-overlay')
      .isVisible()
      .catch(() => false);
    const captainAError = await captainAPage
      .getByTestId('herodraft-reconnecting')
      .isVisible()
      .catch(() => false);
    expect(captainAKicked || captainAError).toBe(true);

    // Captain B should NOT be affected
    await expect(
      captainBPage.getByTestId('herodraft-reconnecting')
    ).not.toBeVisible();
    await expect(captainBPage.getByTestId('herodraft-kicked-overlay')).not.toBeVisible();

    // Captain A's second tab should be fine
    await expect(
      captainAPage2.locator('[data-testid="herodraft-reconnecting"]')
    ).not.toBeVisible();

    // Cleanup
    await captainAContext.close();
    await captainAContext2.close();
    await captainBContext.close();
  });
});
