import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for demo video recording.
 *
 * Key differences from main config:
 * - Video recording always enabled ('on')
 * - 1:1 aspect ratio viewport (800x800)
 * - Videos saved to docs/assets/videos/
 * - Slower execution for better video quality
 * - Single worker for sequential recording
 */
export default defineConfig({
  testDir: './tests/playwright/demo',
  testMatch: /\.demo\.ts$/,

  // Single worker for sequential, predictable recordings
  workers: 1,
  fullyParallel: false,

  // No retries for demos
  retries: 0,
  forbidOnly: true,

  // Reporters
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: 'https://localhost',
    ignoreHTTPSErrors: true,

    // 1:1 aspect ratio for demo videos (Instagram/social-friendly)
    viewport: { width: 800, height: 800 },

    // Always record video for demos
    video: {
      mode: 'on',
      size: { width: 800, height: 800 },
    },

    // Take screenshots at key moments
    screenshot: 'on',

    // Trace for debugging if needed
    trace: 'retain-on-failure',

    // Slower actions for visibility in videos
    actionTimeout: 10_000,
  },

  projects: [
    {
      name: 'demo-chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          // Slow down for demo visibility
          slowMo: 200,
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
      name: 'demo-herodraft',
      testMatch: /herodraft.*\.demo\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        // Headed mode for herodraft (two browsers)
        headless: false,
        launchOptions: {
          slowMo: 150,
          args: [
            '--no-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-dev-shm-usage',
          ],
        },
      },
    },
  ],

  // Longer timeout for demos (5 minutes per test)
  timeout: 300_000,

  expect: {
    timeout: 15_000,
  },

  // Output directory for demo artifacts
  outputDir: 'demo-results/',
});
