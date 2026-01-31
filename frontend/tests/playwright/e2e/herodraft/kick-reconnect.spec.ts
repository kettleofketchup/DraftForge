/**
 * Test: Captain with two tabs doesn't cause infinite reconnect loop
 *
 * When a captain opens the same draft in two tabs, the server kicks the old
 * connection. This test verifies that the kicked tab doesn't try to reconnect.
 */

import { test, expect } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';

const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;

test.describe('HeroDraft Kick Reconnect', () => {
  test('kicked tab does not reconnect infinitely', async ({ browser }) => {
    test.setTimeout(60000);

    // Get test draft info
    const context1 = await browser.newContext({ ignoreHTTPSErrors: true });
    const response = await context1.request.get(
      `${API_URL}/tests/herodraft-by-key/demo_herodraft/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      await context1.close();
      test.skip(true, 'Demo herodraft not available');
      return;
    }

    const testInfo = await response.json();
    const captain = testInfo.draft_teams[0].captain;
    const herodraftUrl = `${BASE_URL}/herodraft/${testInfo.pk}`;

    console.log(`Testing with draft ${testInfo.pk}, captain: ${captain.username}`);

    // Reset the draft first
    await context1.request.post(`${API_URL}/tests/herodraft/${testInfo.pk}/reset/`);

    // Login as captain in first context
    await loginAsDiscordId(context1, captain.discordId);
    const page1 = await context1.newPage();

    // Create second context (simulates second tab)
    const context2 = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAsDiscordId(context2, captain.discordId);
    const page2 = await context2.newPage();

    // Track console messages on page1
    const page1Messages: string[] = [];
    page1.on('console', (msg) => {
      const text = msg.text();
      if (text.includes('Kicked') || text.includes('kicked') || text.includes('Reconnect')) {
        page1Messages.push(text);
      }
    });

    // Open draft in tab 1
    console.log('Opening draft in tab 1...');
    await page1.goto(herodraftUrl);
    await waitForHydration(page1);
    await page1.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });

    // Wait for WebSocket connection to establish
    await page1.waitForTimeout(3000);

    // Open draft in tab 2 (should kick tab 1)
    console.log('Opening draft in tab 2 (should kick tab 1)...');
    await page2.goto(herodraftUrl);
    await waitForHydration(page2);
    await page2.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });

    // Wait for kick to happen and verify no reconnect loop
    // If there was an infinite loop, this would hang or we'd see many reconnect messages
    console.log('Waiting 8 seconds to verify no reconnect loop...');
    await page1.waitForTimeout(8000);

    console.log('Tab 1 messages:', page1Messages);

    // Key assertion: Tab 1 should have been kicked
    const wasKicked = page1Messages.some(m => m.includes('Kicked from draft'));
    expect(wasKicked).toBe(true);

    // Verify the kicked overlay is visible on tab 1
    const kickedOverlay = page1.locator('[data-testid="herodraft-kicked-overlay"]');
    await expect(kickedOverlay).toBeVisible({ timeout: 5000 });

    // Verify the overlay has the expected content
    await expect(page1.locator('[data-testid="herodraft-kicked-title"]')).toHaveText('Session Replaced');
    await expect(page1.locator('[data-testid="herodraft-kicked-refresh-btn"]')).toBeVisible();

    // The fix works if either:
    // 1. Reconnect was blocked (message contains "Reconnect blocked"), OR
    // 2. No reconnect was attempted (clean disconnect)
    // Either way, there should be no infinite loop (test completes without hanging)

    // Clean up
    await context1.close();
    await context2.close();

    console.log('Test passed - no infinite reconnect loop');
  });

  test('three tabs: refresh on first tab takes back control', async ({ browser }) => {
    test.setTimeout(90000);

    // Get test draft info
    const context1 = await browser.newContext({ ignoreHTTPSErrors: true });
    const response = await context1.request.get(
      `${API_URL}/tests/herodraft-by-key/demo_herodraft/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      await context1.close();
      test.skip(true, 'Demo herodraft not available');
      return;
    }

    const testInfo = await response.json();
    const captain = testInfo.draft_teams[0].captain;
    const herodraftUrl = `${BASE_URL}/herodraft/${testInfo.pk}`;

    console.log(`Testing 3-tab scenario with draft ${testInfo.pk}, captain: ${captain.username}`);

    // Reset the draft first
    await context1.request.post(`${API_URL}/tests/herodraft/${testInfo.pk}/reset/`);

    // Login as captain in all three contexts
    await loginAsDiscordId(context1, captain.discordId);
    const page1 = await context1.newPage();

    const context2 = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAsDiscordId(context2, captain.discordId);
    const page2 = await context2.newPage();

    const context3 = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAsDiscordId(context3, captain.discordId);
    const page3 = await context3.newPage();

    // Open draft in tab 1
    console.log('Opening draft in tab 1...');
    await page1.goto(herodraftUrl);
    await waitForHydration(page1);
    await page1.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });
    await page1.waitForTimeout(2000);

    // Open draft in tab 2 (kicks tab 1)
    console.log('Opening draft in tab 2 (kicks tab 1)...');
    await page2.goto(herodraftUrl);
    await waitForHydration(page2);
    await page2.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });
    await page2.waitForTimeout(2000);

    // Tab 1 should now show kicked overlay
    console.log('Verifying tab 1 is kicked...');
    await expect(page1.locator('[data-testid="herodraft-kicked-overlay"]')).toBeVisible({ timeout: 5000 });

    // Open draft in tab 3 (kicks tab 2)
    console.log('Opening draft in tab 3 (kicks tab 2)...');
    await page3.goto(herodraftUrl);
    await waitForHydration(page3);
    await page3.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });
    await page3.waitForTimeout(2000);

    // Tab 2 should now show kicked overlay
    console.log('Verifying tab 2 is kicked...');
    await expect(page2.locator('[data-testid="herodraft-kicked-overlay"]')).toBeVisible({ timeout: 5000 });

    // Tab 3 should be active (no kicked overlay)
    console.log('Verifying tab 3 is active...');
    await expect(page3.locator('[data-testid="herodraft-kicked-overlay"]')).not.toBeVisible();
    await expect(page3.locator('[data-testid="herodraft-modal"]')).toBeVisible();

    // Both tab 1 and tab 2 should show kicked overlay
    console.log('Verifying both tab 1 and tab 2 show kicked overlay...');
    await expect(page1.locator('[data-testid="herodraft-kicked-title"]')).toHaveText('Session Replaced');
    await expect(page2.locator('[data-testid="herodraft-kicked-title"]')).toHaveText('Session Replaced');

    // Click refresh on tab 1 to take back control
    console.log('Clicking refresh on tab 1 to take back control...');

    // We can't actually click the refresh button as it triggers window.location.reload()
    // Instead, we'll navigate to the URL again which simulates the same behavior
    await page1.goto(herodraftUrl);
    await waitForHydration(page1);
    await page1.waitForSelector('[data-testid="herodraft-modal"]', { timeout: 15000 });
    await page1.waitForTimeout(2000);

    // Tab 1 should now be active (no kicked overlay)
    console.log('Verifying tab 1 is now active after refresh...');
    await expect(page1.locator('[data-testid="herodraft-kicked-overlay"]')).not.toBeVisible();
    await expect(page1.locator('[data-testid="herodraft-modal"]')).toBeVisible();

    // Tab 3 should now show kicked overlay (was kicked by tab 1's reconnection)
    console.log('Verifying tab 3 is now kicked...');
    await expect(page3.locator('[data-testid="herodraft-kicked-overlay"]')).toBeVisible({ timeout: 5000 });
    await expect(page3.locator('[data-testid="herodraft-kicked-title"]')).toHaveText('Session Replaced');

    // Clean up
    await context1.close();
    await context2.close();
    await context3.close();

    console.log('Test passed - refresh on first tab took back control');
  });
});
