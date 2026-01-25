import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E tests.
 *
 * Performance Optimizations:
 * - fullyParallel: true - Tests run in parallel within files
 * - workers: 50% of CPUs locally, 2 in CI (shared database limitation)
 * - Sharding support for CI: --shard=1/4 etc
 *
 * Projects:
 * - chromium: General E2E tests with parallel execution
 * - herodraft: Sequential execution for multi-browser draft scenarios
 */
export default defineConfig({
  globalSetup: './tests/playwright/global-setup.ts',
  testDir: './tests/playwright',
  // Only match *.spec.ts files in e2e directory (exclude fixtures/helpers)
  testMatch: /e2e\/.*\.spec\.ts$/,
  // Ignore non-test files (fixtures, helpers, constants, types)
  testIgnore: [
    '**/fixtures/**',
    '**/helpers/**',
    '**/constants.ts',
    '**/*.d.ts',
  ],

  // Enable parallel execution by default (projects can override)
  fullyParallel: true,

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,

  // Workers: Use 50% of CPUs locally for speed, 2 in CI (shared database)
  // Can override with --workers flag or PLAYWRIGHT_WORKERS env var
  workers: process.env.CI ? 2 : '50%',

  // Reporters: html + list locally, add github reporter in CI
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
    ...(process.env.CI ? [['github' as const]] : []),
  ],

  use: {
    baseURL: 'https://localhost',
    // Trace only on retry to save resources
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true, // For self-signed certs in dev

    // Default viewport
    viewport: { width: 1280, height: 720 },

    // Performance: Reuse browser context where possible
    // actionTimeout: 15_000, // Faster timeout for actions
  },

  projects: [
    {
      name: 'chromium',
      // Exclude herodraft tests (run in herodraft project)
      testIgnore: /herodraft/i,
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          // Use system chromium in Docker (set via PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH)
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          args: [
            // Container/WSL compatibility
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
    },
    {
      name: 'herodraft',
      testMatch: /herodraft.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        // Launch headed by default for visual debugging (disabled in CI/Docker)
        headless: !!process.env.CI || !!process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          slowMo: process.env.CI ? 0 : 100, // Slow down only for local debugging
          args: [
            '--no-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
      // Override parallel settings for herodraft tests (multi-browser coordination)
      fullyParallel: false,
    },
  ],

  // Global timeout - 30s for test, but faster action timeout
  timeout: 30_000,

  // Expect timeout - 10s for assertions
  expect: {
    timeout: 10_000,
  },

  // Output directory for test artifacts
  outputDir: 'test-results/',
});
