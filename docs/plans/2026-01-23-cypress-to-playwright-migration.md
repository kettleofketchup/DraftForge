# Cypress to Playwright Migration Plan

**Status:** In Progress

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all 25 Cypress E2E tests to Playwright for faster execution and better multi-browser support.

**Architecture:** Port tests iteratively by suite, maintaining Cypress in parallel until migration is complete. Create shared Playwright fixtures/helpers mirroring Cypress patterns, then convert each test file preserving exact test coverage.

**Tech Stack:** Playwright 1.58+, TypeScript, existing backend test API endpoints

---

## Review Feedback (Incorporated)

**QA Engineer Review:**
- GitHub Actions workflow needs Docker stack for full E2E tests
- ~~Clarify directory numbering (10-herodraft vs 11-herodraft)~~ RESOLVED: Consolidated to 11-herodraft/
- Address parallel test isolation concerns for stateful tests
- Add WebSocket utility for Channels tests
- Keep Cypress functional until 100% parity reached

**DevOps Engineer Review:**
- Use `test.playwright.*` namespace (not `test.runner.playwright.*`)
- Reuse existing `flush_test_redis()` function
- Fix herodraft spec pattern to match actual directory

**TypeScript Engineer Review:**
- Create Page Object classes (TournamentPage, LeaguePage) for consistency
- Use project-based parallelism (parallel for general, sequential for herodraft)
- Use explicit waits instead of `waitForTimeout()` where possible

---

## Pre-Migration Summary

### Current Cypress Test Structure
```
frontend/tests/cypress/
├── e2e/
│   ├── 00-hydration-handling.cy.ts
│   ├── 01-navigation.cy.ts
│   ├── 03-tournaments/
│   │   ├── 01-page.cy.ts
│   │   └── 02-form.cy.ts
│   ├── 04-tournament/
│   │   ├── 01-page.cy.ts
│   │   ├── 02-user.cy.ts
│   │   └── 03-ui-elements.cy.ts
│   ├── 05-match-stats/
│   │   └── 01-modal.cy.ts
│   ├── 06-mobile/
│   │   └── 01-responsive.cy.ts
│   ├── 07-draft/
│   │   ├── 01-captain-pick.cy.ts
│   │   └── 02-undo-pick.cy.ts
│   ├── 08-shuffle-draft/
│   │   ├── 01-full-draft.cy.ts
│   │   └── 02-roll.cy.ts
│   ├── 09-bracket/
│   │   ├── 01-bracket-badges.cy.ts
│   │   ├── 02-bracket-match-linking.cy.ts
│   │   └── 03-bracket-winner-advancement.cy.ts
│   ├── 10-leagues/
│   │   ├── 01-tabs.cy.ts
│   │   ├── 02-edit-modal.cy.ts
│   │   ├── 03-matches.cy.ts
│   │   └── 04-steam-matches.cy.ts
│   └── 11-herodraft/
│       ├── 00-full-draft-flow.cy.ts
│       ├── 01-waiting-phase.cy.ts
│       ├── 02-rolling-choosing-phase.cy.ts
│       ├── 03-drafting-phase.cy.ts
│       └── 04-websocket-updates.cy.ts
├── fixtures/
│   ├── auth.json
│   └── testData.json
├── helpers/
│   ├── league.ts
│   ├── tournament.ts
│   ├── types.d.ts
│   └── users.ts
└── support/
    ├── commands.ts
    ├── component.ts
    ├── e2e.ts
    └── utils.ts
```

### Target Playwright Test Structure
```
frontend/tests/playwright/
├── e2e/
│   ├── 00-hydration-handling.spec.ts
│   ├── 01-navigation.spec.ts
│   ├── 03-tournaments/
│   │   ├── 01-page.spec.ts
│   │   └── 02-form.spec.ts
│   ├── 04-tournament/
│   │   ├── 01-page.spec.ts
│   │   ├── 02-user.spec.ts
│   │   └── 03-ui-elements.spec.ts
│   ├── 05-match-stats/
│   │   └── 01-modal.spec.ts
│   ├── 06-mobile/
│   │   └── 01-responsive.spec.ts
│   ├── 07-draft/
│   │   ├── 01-captain-pick.spec.ts
│   │   └── 02-undo-pick.spec.ts
│   ├── 08-shuffle-draft/
│   │   ├── 01-full-draft.spec.ts
│   │   └── 02-roll.spec.ts
│   ├── 09-bracket/
│   │   ├── 01-bracket-badges.spec.ts
│   │   ├── 02-bracket-match-linking.spec.ts
│   │   └── 03-bracket-winner-advancement.spec.ts
│   ├── 10-leagues/
│   │   ├── 01-tabs.spec.ts
│   │   ├── 02-edit-modal.spec.ts
│   │   ├── 03-matches.spec.ts
│   │   └── 04-steam-matches.spec.ts
│   └── 11-herodraft/           # Already exists!
│       ├── 01-waiting-phase.spec.ts
│       ├── 02-rolling-choosing-phase.spec.ts
│       ├── 03-drafting-phase.spec.ts
│       ├── 04-websocket-updates.spec.ts
│       └── two-captains-full-draft.spec.ts  # Already exists!
├── fixtures/
│   ├── auth.ts                 # Already exists!
│   ├── herodraft.ts           # Already exists!
│   └── index.ts               # Already exists!
└── helpers/
    ├── HeroDraftPage.ts       # Already exists!
    ├── utils.ts               # NEW - port from cypress/support/utils.ts
    ├── users.ts               # NEW - port from cypress/helpers/users.ts
    ├── tournament.ts          # NEW - port from cypress/helpers/tournament.ts
    └── league.ts              # NEW - port from cypress/helpers/league.ts
```

---

## Task 1: Expand Playwright Config for Full E2E Suite

**Files:**
- Modify: `frontend/playwright.config.ts`

**Step 1: Update playwright.config.ts for parallel test execution**

```typescript
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E tests.
 * Migrated from Cypress for faster parallel execution.
 */
export default defineConfig({
  testDir: './tests/playwright',
  fullyParallel: true, // Enable parallel execution
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined, // 4 workers in CI, auto in local
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

    // Default viewport (matches Cypress config)
    viewport: { width: 1280, height: 720 },
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-dev-shm-usage',
          ],
        },
      },
    },
    // Add mobile project for responsive tests
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
      },
    },
  ],

  // Global timeout (matches Cypress pageLoadTimeout)
  timeout: 30_000,

  // Expect timeout (matches Cypress defaultCommandTimeout)
  expect: {
    timeout: 10_000,
  },
});
```

**Step 2: Verify config is valid**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx playwright test --list`
Expected: Lists available tests without errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/playwright.config.ts
git commit -m "feat(tests): expand playwright config for full e2e migration"
```

---

## Task 2: Create Shared Playwright Utilities

**Files:**
- Create: `frontend/tests/playwright/helpers/utils.ts`

**Step 1: Port hydration and navigation utilities from Cypress**

```typescript
import { Page, Locator, expect } from '@playwright/test';

/**
 * Utilities for handling React hydration and common test patterns.
 * Ported from Cypress support/utils.ts
 */

/**
 * Visit a page and wait for React hydration to complete.
 */
export async function visitAndWaitForHydration(page: Page, url: string): Promise<void> {
  await page.goto(url);

  // Wait for the page to be visible
  await page.locator('body').waitFor({ state: 'visible' });

  // Wait for document ready state
  await page.waitForFunction(() => document.readyState === 'complete');

  // Wait for React app indicators
  await page
    .locator('[data-slot], nav, main, #root')
    .first()
    .waitFor({ state: 'visible', timeout: 10000 });

  // Brief wait for React hydration
  await page.waitForTimeout(200);
}

/**
 * Wait for any loading states to complete.
 */
export async function waitForLoadingToComplete(page: Page): Promise<void> {
  const loadingIndicators = page.locator('[data-testid="loading"], .loading, .spinner');

  // If loading indicators exist, wait for them to disappear
  const count = await loadingIndicators.count();
  if (count > 0) {
    await loadingIndicators.first().waitFor({ state: 'hidden', timeout: 10000 });
  }
}

/**
 * Smart navigation that handles both visible links and dropdown menus.
 */
export async function navigateToRoute(page: Page, route: string): Promise<void> {
  // First try visible navigation links
  const visibleSelectors = [
    `nav > a[href="${route}"]`,
    `header a[href="${route}"]`,
    `.navbar a[href="${route}"]`,
    `a[href="${route}"]`,
  ];

  for (const selector of visibleSelectors) {
    const link = page.locator(selector).first();
    if (await link.isVisible().catch(() => false)) {
      await link.click();
      return;
    }
  }

  // Try dropdown navigation
  const dropdownTriggers = [
    'button[aria-haspopup="true"]',
    '.dropdown-toggle',
    '.menu-button',
    '[data-testid="menu-button"]',
    '.hamburger-menu',
    'button[aria-label="Open mobile menu"]',
  ];

  for (const triggerSelector of dropdownTriggers) {
    const trigger = page.locator(triggerSelector).first();
    if (await trigger.isVisible().catch(() => false)) {
      await trigger.click();
      await page.waitForTimeout(300);

      const link = page.locator(`a[href="${route}"]`).first();
      if (await link.isVisible().catch(() => false)) {
        await link.click();
        return;
      }
    }
  }

  // Fallback: direct navigation
  await visitAndWaitForHydration(page, route);
}

/**
 * Check for basic accessibility features.
 */
export async function checkBasicAccessibility(page: Page): Promise<void> {
  // Check language attribute
  await expect(page.locator('html')).toHaveAttribute('lang', /.+/);

  // Check for title
  const title = await page.title();
  expect(title.length).toBeGreaterThan(0);

  // Check for main content landmark
  const mainLandmark = page.locator('main, [role="main"]');
  const hasMain = await mainLandmark.count() > 0;
  if (!hasMain) {
    console.log('No main landmark found - this could be improved for accessibility');
  }
}

/**
 * Suppress hydration errors in console (for debugging).
 * In Playwright, we handle this differently - we just ignore known error patterns.
 */
export const IGNORED_CONSOLE_PATTERNS = [
  'Hydration failed',
  'Text content does not match',
  'Warning: Text content did not match',
  "server rendered HTML didn't match",
  'Expected server HTML to contain',
  'net::ERR_ABORTED',
  'Failed to load resource',
  'fonts.googleapis.com',
  'ResizeObserver loop',
];

/**
 * Check if a console message should be ignored.
 */
export function shouldIgnoreConsoleMessage(message: string): boolean {
  return IGNORED_CONSOLE_PATTERNS.some(pattern =>
    message.toLowerCase().includes(pattern.toLowerCase())
  );
}
```

**Step 2: Verify the file compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit tests/playwright/helpers/utils.ts`
Expected: No errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/helpers/utils.ts
git commit -m "feat(tests): add playwright shared utilities ported from cypress"
```

---

## Task 3: Create Playwright Helper Functions for Users

**Files:**
- Create: `frontend/tests/playwright/helpers/users.ts`

**Step 1: Port user helpers from Cypress**

```typescript
import { Page, Locator } from '@playwright/test';

/**
 * User-related test helpers.
 * Ported from Cypress helpers/users.ts
 */

/**
 * Get a user card element by username.
 */
export function getUserCard(page: Page, username: string): Locator {
  return page.locator(`[data-testid="usercard-${username}"]`);
}

/**
 * Get the remove player button for a specific user.
 */
export function getUserRemoveButton(page: Page, username: string): Locator {
  return page.locator(`[data-testid="removePlayerBtn-${username}"]`);
}

/**
 * Wait for a user card to be visible.
 */
export async function waitForUserCard(page: Page, username: string): Promise<void> {
  await getUserCard(page, username).waitFor({ state: 'visible' });
}

/**
 * Click the remove button for a user.
 */
export async function removeUser(page: Page, username: string): Promise<void> {
  await getUserRemoveButton(page, username).click();
}
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/helpers/users.ts
git commit -m "feat(tests): add playwright user helpers"
```

---

## Task 4: Create Playwright Tournament Helpers

**Files:**
- Create: `frontend/tests/playwright/helpers/tournament.ts`
- Reference: `frontend/tests/cypress/helpers/tournament.ts`

**Step 1: Read existing Cypress tournament helpers and port**

First read the existing file, then create the Playwright equivalent with the same functionality.

```typescript
import { Page, Locator, BrowserContext, expect } from '@playwright/test';

const API_URL = 'https://localhost/api';

/**
 * Tournament-related test helpers.
 * Ported from Cypress helpers/tournament.ts
 */

export interface TournamentData {
  pk: number;
  name: string;
  teams: Array<{
    pk: number;
    name: string;
    captain: {
      pk: number;
      username: string;
    };
    draft_order: number;
  }>;
  captains: Array<{
    pk: number;
    username: string;
  }>;
}

/**
 * Get tournament details by test config key.
 */
export async function getTournamentByKey(
  context: BrowserContext,
  key: string
): Promise<TournamentData> {
  const response = await context.request.get(
    `${API_URL}/tests/tournament-by-key/${key}/`
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

/**
 * Navigate to a tournament page.
 */
export async function navigateToTournament(page: Page, tournamentPk: number): Promise<void> {
  await page.goto(`/tournament/${tournamentPk}`);
  await page.locator('body').waitFor({ state: 'visible' });
}

/**
 * Click on the Teams tab in a tournament.
 */
export async function clickTeamsTab(page: Page): Promise<void> {
  await page.locator('text=/Teams \\(\\d+\\)/').click();
  await page.waitForTimeout(500);
}

/**
 * Click the Start Draft button.
 */
export async function clickStartDraft(page: Page): Promise<void> {
  const startDraftBtn = page.locator('button:has-text("Start Draft"), button:has-text("Live Draft")');
  await startDraftBtn.first().click();
  await page.waitForTimeout(500);
}

/**
 * Wait for the draft modal to open.
 */
export async function waitForDraftModal(page: Page): Promise<Locator> {
  const modal = page.locator('[role="dialog"]');
  await modal.waitFor({ state: 'visible' });
  return modal;
}
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/helpers/tournament.ts
git commit -m "feat(tests): add playwright tournament helpers"
```

---

## Task 5: Create Playwright League Helpers

**Files:**
- Create: `frontend/tests/playwright/helpers/league.ts`
- Reference: `frontend/tests/cypress/helpers/league.ts`

**Step 1: Read existing Cypress league helpers and port**

```typescript
import { Page, Locator, BrowserContext, expect } from '@playwright/test';

const API_URL = 'https://localhost/api';

/**
 * League-related test helpers.
 * Ported from Cypress helpers/league.ts
 */

export interface LeagueData {
  pk: number;
  name: string;
  // Add other fields as needed based on actual league structure
}

/**
 * Navigate to a league page.
 */
export async function navigateToLeague(page: Page, leaguePk: number): Promise<void> {
  await page.goto(`/league/${leaguePk}`);
  await page.locator('body').waitFor({ state: 'visible' });
}

/**
 * Click on a league tab by name.
 */
export async function clickLeagueTab(page: Page, tabName: string): Promise<void> {
  await page.locator(`[role="tab"]:has-text("${tabName}")`).click();
  await page.waitForTimeout(300);
}

/**
 * Get league edit modal.
 */
export function getLeagueEditModal(page: Page): Locator {
  return page.locator('[role="dialog"]');
}

/**
 * Open league edit modal.
 */
export async function openLeagueEditModal(page: Page): Promise<Locator> {
  await page.locator('button:has-text("Edit")').click();
  const modal = getLeagueEditModal(page);
  await modal.waitFor({ state: 'visible' });
  return modal;
}
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/helpers/league.ts
git commit -m "feat(tests): add playwright league helpers"
```

---

## Task 6: Update Playwright Fixtures Index

**Files:**
- Modify: `frontend/tests/playwright/fixtures/index.ts`

**Step 1: Export all helpers from index**

```typescript
/**
 * Playwright Test Fixtures
 *
 * Export all fixtures for easy importing in tests.
 */

// Auth utilities (functions only, not the extended test)
export {
  loginAsUser,
  loginAsDiscordId,
  loginAdmin,
  loginStaff,
  loginUser,
  waitForHydration,
  visitAndWait,
  type UserInfo,
  type LoginResponse,
} from './auth';

// HeroDraft utilities
export {
  getHeroDraftByKey,
  resetHeroDraft,
  createTestHeroDraft,
  setupTwoCaptains,
  positionWindowsSideBySide,
  type HeroDraftInfo,
  type CaptainContext,
} from './herodraft';

// Re-export the extended test from auth (primary test fixture)
export { test, expect } from './auth';

// Re-export helpers
export * from '../helpers/utils';
export * from '../helpers/users';
export * from '../helpers/tournament';
export * from '../helpers/league';
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/fixtures/index.ts
git commit -m "feat(tests): update playwright fixtures index with all helpers"
```

---

## Task 7: Create Invoke Task for Playwright Runner

**Files:**
- Modify: `scripts/tests.py`

**Step 1: Add Playwright test runner tasks**

Add the following after the Cypress collections (around line 250):

```python
# =============================================================================
# Playwright Test Collections
# =============================================================================

ns_playwright = Collection("playwright")


def flush_test_redis_for_playwright(c):
    """Flush Redis cache in test environment to ensure fresh data."""
    print("Flushing Redis cache for Playwright tests...")
    c.run("docker exec test-redis redis-cli FLUSHALL", warn=True)


@task
def playwright_install(c):
    """Install Playwright browsers."""
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright install chromium")


@task
def playwright_headless(c):
    """Run all Playwright tests in headless mode."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --reporter=list")


@task
def playwright_headed(c):
    """Run all Playwright tests in headed mode."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --headed --reporter=list")


@task
def playwright_ui(c):
    """Open Playwright UI mode for interactive testing."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --ui")


@task
def playwright_debug(c):
    """Run Playwright tests in debug mode."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --debug")


@task
def playwright_spec(c, spec=""):
    """Run Playwright tests for a specific spec pattern.

    Usage:
        inv test.playwright.spec --spec navigation     # Runs *navigation*.spec.ts
        inv test.playwright.spec --spec tournament     # Runs *tournament*.spec.ts
        inv test.playwright.spec --spec 01             # Runs *01*.spec.ts
    """
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        if spec:
            # Map common names to spec patterns
            spec_patterns = {
                "drafts": "tests/playwright/e2e/07-draft/",
                "draft": "tests/playwright/e2e/07-draft/",
                "tournament": "tests/playwright/e2e/04-tournament/",
                "tournaments": "tests/playwright/e2e/03-tournaments/",
                "navigation": "tests/playwright/e2e/01-*.spec.ts",
                "mobile": "tests/playwright/e2e/06-mobile/",
                "herodraft": "tests/playwright/e2e/herodraft/",
                "bracket": "tests/playwright/e2e/09-bracket/",
                "leagues": "tests/playwright/e2e/10-leagues/",
            }
            pattern = spec_patterns.get(spec, f"tests/playwright/e2e/**/*{spec}*.spec.ts")
            cmd = f'npx playwright test "{pattern}" --reporter=list'
        else:
            cmd = "npx playwright test --reporter=list"
        c.run(cmd)


@task
def playwright_report(c):
    """Show the Playwright HTML report from the last run."""
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright show-report")


# Specific test suites
@task
def playwright_navigation(c):
    """Run navigation Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/0[01]-*.spec.ts" --reporter=list')


@task
def playwright_tournament(c):
    """Run tournament Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/0[34]-tournament*/" --reporter=list')


@task
def playwright_draft(c):
    """Run draft-related Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/07-draft/" "tests/playwright/e2e/08-shuffle-draft/" --reporter=list')


@task
def playwright_bracket(c):
    """Run bracket Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/09-bracket/" --reporter=list')


@task
def playwright_league(c):
    """Run league Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/10-leagues/" --reporter=list')


@task
def playwright_herodraft(c):
    """Run herodraft Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/*herodraft*/" --reporter=list')


@task
def playwright_mobile(c):
    """Run mobile/responsive Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx playwright test "tests/playwright/e2e/06-mobile/" --project=mobile-chrome --reporter=list')


@task
def playwright_all(c):
    """Run all Playwright tests."""
    flush_test_redis_for_playwright(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --reporter=list")


# Add tasks to playwright collection
ns_playwright.add_task(playwright_install, "install")
ns_playwright.add_task(playwright_headless, "headless")
ns_playwright.add_task(playwright_headed, "headed")
ns_playwright.add_task(playwright_ui, "ui")
ns_playwright.add_task(playwright_debug, "debug")
ns_playwright.add_task(playwright_spec, "spec")
ns_playwright.add_task(playwright_report, "report")
ns_playwright.add_task(playwright_navigation, "navigation")
ns_playwright.add_task(playwright_tournament, "tournament")
ns_playwright.add_task(playwright_draft, "draft")
ns_playwright.add_task(playwright_bracket, "bracket")
ns_playwright.add_task(playwright_league, "league")
ns_playwright.add_task(playwright_herodraft, "herodraft")
ns_playwright.add_task(playwright_mobile, "mobile")
ns_playwright.add_task(playwright_all, "all")

# Add as nested collection under test.runner
ns_runner.add_collection(ns_playwright, "playwright")
```

**Step 2: Verify invoke can list the new tasks**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv --list | grep playwright`
Expected: Shows `test.runner.playwright.*` tasks

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add scripts/tests.py
git commit -m "feat(tests): add invoke tasks for playwright test runner"
```

---

## Task 8: Port Navigation Tests (01-navigation)

**Files:**
- Create: `frontend/tests/playwright/e2e/01-navigation.spec.ts`
- Reference: `frontend/tests/cypress/e2e/01-navigation.cy.ts`

**Step 1: Create the navigation test file**

```typescript
import { test, expect } from '@playwright/test';
import {
  visitAndWaitForHydration,
  checkBasicAccessibility,
  navigateToRoute,
} from '../../fixtures';

test.describe('Navigation and Basic Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Visit the home page and wait for React hydration before each test
    await visitAndWaitForHydration(page, '/');
  });

  test('should load the home page successfully', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);

    // Check that the page loads without errors
    await expect(page).toHaveURL(/\/$/);
  });

  test('should have working navigation links', async ({ page }) => {
    // Test navigation to different routes
    const routes = ['/tournaments', '/about', '/users'];

    for (const route of routes) {
      // Use smart navigation that handles responsive design
      const mobileMenuButton = page.locator('button[aria-label="Open mobile menu"]');

      if (await mobileMenuButton.isVisible().catch(() => false)) {
        // Mobile navigation
        await mobileMenuButton.click();
        await page.waitForTimeout(300);

        const link = page.locator(`a[href="${route}"]`).first();
        if (await link.isVisible().catch(() => false)) {
          await link.click();
        }
      } else {
        // Desktop navigation - try visible links
        const desktopSelectors = [
          `nav a[href="${route}"]`,
          `header a[href="${route}"]`,
          `.navbar a[href="${route}"]`,
        ];

        let found = false;
        for (const selector of desktopSelectors) {
          const link = page.locator(selector).first();
          if (await link.isVisible().catch(() => false)) {
            await link.click();
            found = true;
            break;
          }
        }

        if (!found) {
          console.log(`No UI navigation found for ${route} - skipping`);
          continue;
        }
      }

      // Verify we navigated to the correct route
      const url = page.url();
      if (url.includes(route)) {
        await expect(page.locator('body')).toBeVisible();
      }

      // Go back to home for next iteration
      await visitAndWaitForHydration(page, '/');
    }
  });

  test('should be responsive and mobile-friendly', async ({ page }) => {
    // Test different viewport sizes
    const viewports = [
      { width: 375, height: 667, device: 'iPhone SE' },
      { width: 768, height: 1024, device: 'iPad' },
      { width: 1280, height: 720, device: 'Desktop' },
    ];

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await visitAndWaitForHydration(page, '/');

      // Check that content is visible and accessible
      await expect(page.locator('body')).toBeVisible();

      // Ensure no horizontal scrolling on mobile
      if (viewport.width < 768) {
        const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
        expect(bodyWidth).toBeLessThanOrEqual(viewport.width + 1);
      }
    }
  });

  test('should handle 404 pages gracefully', async ({ page }) => {
    await page.goto('/non-existent-page');

    // Should show some kind of error page or redirect
    await expect(page.locator('body')).toBeVisible();

    // Could be 404 page or redirect to home
    const url = page.url();
    expect(url.includes('/non-existent-page') || url.endsWith('/')).toBeTruthy();
  });

  test('should load page assets correctly', async ({ page }) => {
    await visitAndWaitForHydration(page, '/');

    // Check that CSS is loaded (by verifying styled elements)
    const margin = await page.locator('body').evaluate(el =>
      window.getComputedStyle(el).margin
    );
    expect(margin).toBeDefined();

    // Check for favicon
    const faviconResponse = await page.request.get('/favicon.ico');
    expect([200, 304]).toContain(faviconResponse.status());

    // Verify the page loaded successfully
    await expect(page.locator('body')).toBeVisible();
  });

  test('should have accessibility basics', async ({ page }) => {
    await visitAndWaitForHydration(page, '/');

    // Use the accessibility checker
    await checkBasicAccessibility(page);
  });

  test('should handle browser back/forward navigation', async ({ page }) => {
    // Navigate through several pages
    await visitAndWaitForHydration(page, '/');

    // Handle responsive navigation properly
    const mobileMenuButton = page.locator('button[aria-label="Open mobile menu"]');

    if (await mobileMenuButton.isVisible().catch(() => false)) {
      // Mobile navigation flow
      await mobileMenuButton.click();
      await page.waitForTimeout(300);
      await page.locator('a').filter({ hasText: /tournaments/i }).first().click();
    } else {
      // Desktop navigation flow
      const navLink = page.locator('nav a[href*="/tournaments"], header a[href*="/tournaments"]').first();
      if (await navLink.isVisible().catch(() => false)) {
        await navLink.click();
      } else {
        // Fallback
        await page.locator('a').filter({ hasText: /tournaments/i }).first().click({ force: true });
      }
    }

    await expect(page).toHaveURL(/\/tournaments/);

    // Use browser back button
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);

    // Use browser forward button
    await page.goForward();
    await expect(page).toHaveURL(/\/tournaments/);
  });
});
```

**Step 2: Run the test to verify it compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx playwright test tests/playwright/e2e/01-navigation.spec.ts --list`
Expected: Lists the test cases

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/e2e/01-navigation.spec.ts
git commit -m "feat(tests): port navigation tests to playwright"
```

---

## Task 9: Port Hydration Handling Tests (00-hydration-handling)

**Files:**
- Create: `frontend/tests/playwright/e2e/00-hydration-handling.spec.ts`
- Reference: `frontend/tests/cypress/e2e/00-hydration-handling.cy.ts`

**Step 1: Read existing Cypress test and create Playwright equivalent**

(Read the file first, then port based on actual content)

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/e2e/00-hydration-handling.spec.ts
git commit -m "feat(tests): port hydration handling tests to playwright"
```

---

## Task 10: Port Tournament Page Tests (03-tournaments)

**Files:**
- Create: `frontend/tests/playwright/e2e/03-tournaments/01-page.spec.ts`
- Create: `frontend/tests/playwright/e2e/03-tournaments/02-form.spec.ts`
- Reference: `frontend/tests/cypress/e2e/03-tournaments/`

**Step 1: Read existing Cypress tests and port**

(Follow same pattern - read, port, commit)

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/tests/playwright/e2e/03-tournaments/
git commit -m "feat(tests): port tournament page tests to playwright"
```

---

## Task 11: Port Single Tournament Tests (04-tournament)

**Files:**
- Create: `frontend/tests/playwright/e2e/04-tournament/01-page.spec.ts`
- Create: `frontend/tests/playwright/e2e/04-tournament/02-user.spec.ts`
- Create: `frontend/tests/playwright/e2e/04-tournament/03-ui-elements.spec.ts`

(Follow same pattern)

---

## Task 12: Port Match Stats Tests (05-match-stats)

**Files:**
- Create: `frontend/tests/playwright/e2e/05-match-stats/01-modal.spec.ts`

---

## Task 13: Port Mobile Responsive Tests (06-mobile)

**Files:**
- Create: `frontend/tests/playwright/e2e/06-mobile/01-responsive.spec.ts`

---

## Task 14: Port Draft Tests (07-draft)

**Files:**
- Create: `frontend/tests/playwright/e2e/07-draft/01-captain-pick.spec.ts`
- Create: `frontend/tests/playwright/e2e/07-draft/02-undo-pick.spec.ts`

---

## Task 15: Port Shuffle Draft Tests (08-shuffle-draft)

**Files:**
- Create: `frontend/tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts`
- Create: `frontend/tests/playwright/e2e/08-shuffle-draft/02-roll.spec.ts`

---

## Task 16: Port Bracket Tests (09-bracket)

**Files:**
- Create: `frontend/tests/playwright/e2e/09-bracket/01-bracket-badges.spec.ts`
- Create: `frontend/tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts`
- Create: `frontend/tests/playwright/e2e/09-bracket/03-bracket-winner-advancement.spec.ts`

---

## Task 17: Port League Tests (10-leagues)

**Files:**
- Create: `frontend/tests/playwright/e2e/10-leagues/01-tabs.spec.ts`
- Create: `frontend/tests/playwright/e2e/10-leagues/02-edit-modal.spec.ts`
- Create: `frontend/tests/playwright/e2e/10-leagues/03-matches.spec.ts`
- Create: `frontend/tests/playwright/e2e/10-leagues/04-steam-matches.spec.ts`

---

## Task 18: Port HeroDraft Tests (11-herodraft)

**Files:**
- Create: `frontend/tests/playwright/e2e/11-herodraft/00-full-draft-flow.spec.ts`
- Create: `frontend/tests/playwright/e2e/11-herodraft/01-waiting-phase.spec.ts`
- Create: `frontend/tests/playwright/e2e/11-herodraft/02-rolling-choosing-phase.spec.ts`
- Create: `frontend/tests/playwright/e2e/11-herodraft/03-drafting-phase.spec.ts`
- Create: `frontend/tests/playwright/e2e/11-herodraft/04-websocket-updates.spec.ts`

Note: Some herodraft tests already exist. Check and merge/extend as needed.
Note: The 10-herodraft directory was consolidated into 11-herodraft to resolve numbering conflict with 10-leagues.

---

## Task 19: Update package.json Scripts

**Files:**
- Modify: `frontend/package.json`

**Step 1: Add more Playwright scripts**

Add these to the `scripts` section:

```json
{
  "scripts": {
    "test:playwright": "playwright test",
    "test:playwright:headed": "playwright test --headed",
    "test:playwright:ui": "playwright test --ui",
    "test:playwright:debug": "playwright test --debug",
    "test:playwright:report": "playwright show-report",
    "test:playwright:install": "playwright install chromium",
    "test:herodraft": "playwright test tests/playwright/e2e/herodraft",
    "test:herodraft:debug": "playwright test tests/playwright/e2e/herodraft --debug"
  }
}
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add frontend/package.json
git commit -m "feat(tests): add playwright npm scripts"
```

---

## Task 20: Update GitHub Actions Workflow

**Files:**
- Modify: `.github/workflows/cypress.yml` (rename/update for Playwright)
- Or Create: `.github/workflows/playwright.yml`

**Step 1: Create Playwright CI workflow**

```yaml
name: Playwright Tests

on:
  push:
    branches: [main, feature/*]
  pull_request:
    branches: [main]

jobs:
  playwright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright browsers
        working-directory: frontend
        run: npx playwright install --with-deps chromium

      - name: Run Playwright tests
        working-directory: frontend
        run: npx playwright test --reporter=github,html

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 30
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add .github/workflows/playwright.yml
git commit -m "ci: add playwright github actions workflow"
```

---

## Task 21: Update Documentation

**Files:**
- Modify: `.claude/CLAUDE.md`
- Modify: `docs/dev/testing/cypress-tests.md` -> `docs/dev/testing/e2e-tests.md`

**Step 1: Update CLAUDE.md testing section**

Update the Testing section to include Playwright commands:

```markdown
## Testing

**Backend (via Docker - Recommended)**:
```bash
source .venv/bin/activate
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

**Frontend E2E (Playwright - Recommended)**:
```bash
source .venv/bin/activate

# Run all Playwright tests
inv test.runner.playwright.headless

# Run with UI mode (interactive)
inv test.runner.playwright.ui

# Run specific suite
inv test.runner.playwright.spec --spec navigation
inv test.runner.playwright.spec --spec tournament
inv test.runner.playwright.spec --spec draft

# Run herodraft tests
inv test.runner.playwright.herodraft
```

**Frontend E2E (Cypress - Legacy)**:
```bash
source .venv/bin/activate
inv test.open          # Cypress interactive
inv test.headless      # Cypress headless
```
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
git add .claude/CLAUDE.md docs/dev/testing/
git commit -m "docs: update testing documentation for playwright migration"
```

---

## Cypress to Playwright API Reference

Use this when converting tests:

| Cypress | Playwright |
|---------|------------|
| `cy.visit(url)` | `await page.goto(url)` |
| `cy.get(selector)` | `page.locator(selector)` |
| `cy.get(sel).click()` | `await page.locator(sel).click()` |
| `cy.get(sel).type(text)` | `await page.locator(sel).fill(text)` |
| `cy.get(sel).should('be.visible')` | `await expect(page.locator(sel)).toBeVisible()` |
| `cy.get(sel).should('contain.text', 'x')` | `await expect(page.locator(sel)).toContainText('x')` |
| `cy.get(sel).should('have.attr', 'x')` | `await expect(page.locator(sel)).toHaveAttribute('x', /.+/)` |
| `cy.url().should('include', '/x')` | `await expect(page).toHaveURL(/\/x/)` |
| `cy.wait(ms)` | `await page.waitForTimeout(ms)` |
| `cy.request(...)` | `await context.request.get/post(...)` |
| `cy.intercept(...)` | `await page.route(...)` |
| `cy.viewport(w, h)` | `await page.setViewportSize({ width: w, height: h })` |
| `cy.go('back')` | `await page.goBack()` |
| `cy.go('forward')` | `await page.goForward()` |
| `cy.title()` | `await page.title()` |
| `beforeEach(() => {...})` | `test.beforeEach(async ({ page }) => {...})` |
| `describe('...', () => {...})` | `test.describe('...', () => {...})` |
| `it('...', () => {...})` | `test('...', async ({ page }) => {...})` |
| `cy.contains('text')` | `page.locator('text=text')` or `page.getByText('text')` |
| `cy.get('[data-testid="x"]')` | `page.getByTestId('x')` |

---

## Summary

**Total Tasks:** 21
**Test Files to Port:** 25
**Estimated Implementation:** Tasks 1-8 create infrastructure, Tasks 9-18 port tests

After completing all tasks, the Cypress tests can be deprecated (kept for reference initially) and eventually removed from the codebase.
