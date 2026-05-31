import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E tests.
 *
 * Performance Optimizations:
 * - fullyParallel: true - Tests run in parallel within files
 * - workers: 1 by default (herodraft tests share a single draft + Redis keys)
 * - Override with --workers=2 or PLAYWRIGHT_WORKERS=2 for chromium-only runs
 * - Sharding support for CI: --shard=1/4 etc
 *
 * Projects:
 * - chromium: General E2E tests with parallel execution
 * - herodraft: Sequential execution for multi-browser draft scenarios (depends on chromium)
 * - mobile-pixel5 / mobile-iphone13: Mobile-viewport specs under e2e/mobile/.
 *   iPhone 13 forces browserName: 'chromium' so it runs in the same Docker
 *   image as the rest of the suite (no webkit install required).
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
  // Retry flaky tests: 2 in CI, 1 locally to catch timing issues early
  retries: process.env.CI ? 2 : 1,

  // Workers: Default to 1 to prevent herodraft parallel conflicts (shared draft + Redis keys).
  // Herodraft tests all use the same draft; parallel execution causes captain kick conflicts.
  // Override with --workers=2 for chromium-only runs, or via PLAYWRIGHT_WORKERS env var.
  workers: process.env.PLAYWRIGHT_WORKERS ? parseInt(process.env.PLAYWRIGHT_WORKERS) : 1,

  // Reporters: html + list locally, add github reporter in CI. The
  // health-probe reporter pings /api/healthz/ after every test and writes a
  // JSONL timeseries to test-results/run-logs/ — used to correlate transient
  // first-attempt timeouts with backend pressure across the run.
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
    ['./tests/playwright/reporters/health-probe-reporter.ts'],
    ...(process.env.CI ? [['github', {}] as ['github', Record<string, unknown>]] : []),
  ],

  use: {
    baseURL: 'https://localhost',
    // Record traces for every test, keep them only when the test fails. This
    // captures the *failing* attempt itself, not just the retry — critical for
    // diagnosing first-attempt timeouts that pass on retry. (Was
    // 'on-first-retry', which gave us only the retry trace.)
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Disable video in CI to speed up tests, retain on failure locally
    video: process.env.CI ? 'off' : 'retain-on-failure',
    ignoreHTTPSErrors: true, // For self-signed certs in dev

    // Default viewport
    viewport: { width: 1280, height: 720 },

    // Pin locale to en-US for deterministic regression assertions (without it, Playwright inherits host OS locale)
    locale: 'en-US',

    // Action timeout - 15s max for clicks/fills (faster failure than test timeout)
    actionTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      // Exclude herodraft tests (run in herodraft project), mobile specs
      // (which live under e2e/mobile/ and run in the mobile-* projects),
      // and 16-events specs (run in events-sequential project — those tests
      // share a single seeded event PK from getEventsTestData and race on
      // start_roll_call / resetEventsData when workers > 1 in the same shard).
      testIgnore: [/herodraft/i, /e2e\/mobile\//, /e2e\/16-events\//],
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
      name: 'events-sequential',
      testMatch: /e2e\/16-events\/.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        headless: true,
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          args: [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
      // 16-events specs share a single seeded event PK (returned by
      // getEventsTestData). Each file mutates event state independently —
      // running two files in parallel races on resetEventsData /
      // start_roll_call / reopen_signups. test.describe.serial only
      // protects within a file; this project serializes ACROSS files too.
      dependencies: ['chromium'],
      fullyParallel: false,
    },
    {
      name: 'herodraft',
      testMatch: /herodraft.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        // Always headless — visible browsers steal user focus during local
        // runs. For visual debugging, open `test-results/.../trace.zip` via
        // `npx playwright show-trace` instead.
        headless: true,
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          slowMo: 0,
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
      // Herodraft tests share a single draft in the DB + Redis captain channel keys,
      // so they must not run in parallel with each other. Run after chromium project
      // to avoid competing for workers, and disable parallel execution.
      dependencies: ['chromium'],
      fullyParallel: false,
    },
    {
      name: 'demo',
      testDir: './tests/playwright/demo',
      testMatch: /.*\.demo\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        headless: true,
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          slowMo: 100, // Slow for video recording
          args: [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
      // Demo tests run sequentially (video recording)
      fullyParallel: false,
      // Longer timeout for demo recordings
      timeout: 300_000,
    },
    {
      name: 'mobile-pixel5',
      testMatch: /e2e\/mobile\/.*\.spec\.ts$/,
      use: {
        ...devices['Pixel 5'],
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          args: [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
    },
    {
      name: 'mobile-iphone13',
      testMatch: /e2e\/mobile\/.*\.spec\.ts$/,
      use: {
        ...devices['iPhone 13'],
        // Force chromium so this runs in the same image as the rest of CI
        // (no separate webkit install). The iPhone 13 viewport, user-agent
        // string, deviceScaleFactor, and hasTouch flag still apply.
        browserName: 'chromium',
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          args: [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
    },
    {
      name: 'mobile-iphone-se',
      testMatch: /e2e\/mobile\/.*\.spec\.ts$/,
      use: {
        // iPhone SE 375x667 — the actual width the user reported overflow at.
        ...devices['iPhone SE'],
        browserName: 'chromium',
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
          args: [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
          ],
        },
      },
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
