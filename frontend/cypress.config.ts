import { defineConfig } from 'cypress';

export default defineConfig({
  e2e: {
    experimentalStudio: true, //fixes hydration issues
    baseUrl: 'https://localhost',
    viewportWidth: 1280,
    viewportHeight: 720,
    video: false,
    screenshotOnRunFailure: true,
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
    specPattern: 'tests/cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    supportFile: 'tests/cypress/support/e2e.ts',
    fixturesFolder: 'tests/cypress/fixtures',
    downloadsFolder: 'tests/cypress/downloads',
    screenshotsFolder: 'tests/cypress/screenshots',
    videosFolder: 'tests/cypress/videos',
  },

  component: {
    devServer: {
      framework: 'react',
      bundler: 'vite',
    },
    specPattern: 'tests/cypress/component/**/*.cy.{js,jsx,ts,tsx}',
    supportFile: 'tests/cypress/support/component.ts',
  },

  env: {
    // Environment variables for tests
    theme: 'dark',

    apiUrl: 'https://localhost/api',
    coverage: false,
  },

  defaultCommandTimeout: 10000,
  requestTimeout: 10000,
  responseTimeout: 10000,
  pageLoadTimeout: 30000,

  retries: {
    runMode: 2,
    openMode: 0,
  },

  experimentalStudio: true,
  experimentalWebKitSupport: true,
});
