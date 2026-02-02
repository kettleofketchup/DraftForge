/**
 * Test Environment Utilities
 *
 * Provides functions to detect test/dev environments and control
 * test-only features in the frontend.
 *
 * Test features (like "Login as User" button) are only shown when:
 * 1. import.meta.env.DEV is true (development mode, not production)
 * 2. NOT running in Playwright (window.playwright is not set)
 *
 * This ensures test helpers are:
 * - Tree-shaken out of production builds
 * - Hidden during Playwright test runs and demo recordings
 */

/**
 * Check if Playwright is running (runtime check).
 * Playwright tests inject window.playwright = true via addInitScript.
 * Demo recordings also use this to disable test helpers.
 */
export function isPlaywrightRunning(): boolean {
  if (typeof window === 'undefined') return false;
  return 'playwright' in window && (window as Window & { playwright?: boolean }).playwright === true;
}

/**
 * Check if test-only UI features should be shown.
 * Returns true only when:
 * 1. Running in dev mode (import.meta.env.DEV)
 * 2. NOT running under Playwright (for clean demos/screenshots)
 *
 * Same pattern used in root.tsx for react-scan.
 */
export function shouldShowTestFeatures(): boolean {
  return import.meta.env.DEV && !isPlaywrightRunning();
}

/**
 * Login as a specific user by Discord ID.
 * Only works when backend has TEST_ENDPOINTS enabled.
 *
 * @param discordId - The Discord ID of the user to login as
 * @returns Promise that resolves when login is complete
 */
export async function loginAsDiscordId(discordId: string): Promise<void> {
  const response = await fetch('/api/tests/login-as-discord/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ discord_id: discordId }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Login failed: ${response.status} - ${text}`);
  }

  // Reload page to reflect new session
  window.location.reload();
}
