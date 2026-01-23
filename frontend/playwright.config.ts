import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E tests.
 *
 * Projects:
 * - chromium: General E2E tests with parallel execution
 * - mobile-chrome: Mobile viewport testing with Pixel 5
 * - herodraft: Sequential execution for multi-browser draft scenarios
 */
export default defineConfig({
  testDir: './tests/playwright',

  // Enable parallel execution by default (projects can override)
  fullyParallel: true,

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,

  // Default workers for parallel tests (herodraft project overrides this)
  workers: process.env.CI ? 2 : undefined,

  // Reporters: html + list locally, add github reporter in CI
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
    ...(process.env.CI ? [['github' as const]] : []),
  ],

  use: {
    baseURL: 'https://localhost',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true, // For self-signed certs in dev

    // Default viewport
    viewport: { width: 1280, height: 720 },
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            // WSL compatibility
            '--disable-gpu',
            '--disable-dev-shm-usage',
          ],
        },
      },
    },
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        launchOptions: {
          args: [
            // WSL compatibility
            '--disable-gpu',
            '--disable-dev-shm-usage',
          ],
        },
      },
    },
    {
      name: 'herodraft',
      testMatch: /herodraft.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        // Launch headed by default for visual debugging
        headless: false,
        launchOptions: {
          slowMo: 100, // Slow down for visibility
          args: [
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            // WSL compatibility
            '--disable-gpu',
            '--disable-dev-shm-usage',
          ],
        },
      },
      // Override parallel settings for herodraft tests
      fullyParallel: false,
    },
  ],

  // Global timeout matching Cypress (30s)
  timeout: 30_000,

  // Expect timeout matching Cypress (10s)
  expect: {
    timeout: 10_000,
  },
});
