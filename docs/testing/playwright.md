# Playwright E2E Testing

This document covers Playwright end-to-end testing for the DTX Website.

## Overview

Playwright is the recommended E2E testing framework, offering:

- **Parallel execution** - Tests run concurrently for faster feedback
- **Multiple browser support** - Chromium, mobile viewports
- **Auto-waiting** - Built-in smart waits for elements
- **Trace viewer** - Debug failed tests with screenshots and DOM snapshots

## Quick Start

```bash
source .venv/bin/activate

# Install Playwright browsers (first time only)
inv test.playwright.install

# Run all tests headless
inv test.playwright.headless

# Run tests with visible browser
inv test.playwright.headed

# Open Playwright UI for interactive debugging
inv test.playwright.ui
```

## Test Structure

```
frontend/tests/playwright/
├── e2e/                    # Test specs organized by feature
│   ├── 00-hydration-handling.spec.ts
│   ├── 01-navigation.spec.ts
│   ├── 03-tournaments/     # Tournament list tests
│   ├── 04-tournament/      # Single tournament tests
│   ├── 05-match-stats/     # Match statistics tests
│   ├── 06-mobile/          # Mobile responsive tests
│   ├── 07-draft/           # Captain draft tests
│   ├── 08-shuffle-draft/   # Shuffle draft tests
│   ├── 09-bracket/         # Bracket display tests
│   ├── 10-leagues/         # League tests
│   └── herodraft/          # HeroDraft multi-browser tests
├── fixtures/               # Test fixtures and auth helpers
│   ├── auth.ts             # Authentication fixtures
│   ├── herodraft.ts        # HeroDraft-specific fixtures
│   └── index.ts            # Re-exports all fixtures
├── helpers/                # Page objects and utilities
│   ├── utils.ts            # Shared utilities
│   ├── users.ts            # User card helpers
│   ├── tournament.ts       # TournamentPage class
│   ├── league.ts           # LeaguePage class
│   └── HeroDraftPage.ts    # HeroDraftPage class
└── global-setup.ts         # Pre-test data caching
```

## Running Tests

### By Category

```bash
# Navigation tests
inv test.playwright.navigation

# Tournament tests
inv test.playwright.tournament

# Draft tests
inv test.playwright.draft

# Bracket tests
inv test.playwright.bracket

# League tests
inv test.playwright.league

# Mobile responsive tests
inv test.playwright.mobile

# HeroDraft multi-browser tests
inv test.playwright.herodraft
```

### By Spec Pattern

```bash
# Run tests matching grep pattern
inv test.playwright.spec --spec bracket

# Run tests matching pattern (not a file path)
inv test.playwright.spec --spec navigation

# Run tests matching pattern
inv test.playwright.spec --spec draft
```

### Debug Mode

```bash
# Run with Playwright Inspector
inv test.playwright.debug

# Open UI mode for visual debugging
inv test.playwright.ui
```

## Performance Optimization

### Local Parallel Execution

Tests run in parallel using 50% of CPU cores by default:

```bash
# Default (50% of CPUs)
inv test.playwright.headless

# Specify worker count
inv test.playwright.headless --args="--workers=4"

# Single worker for debugging
inv test.playwright.headless --args="--workers=1"
```

### CI Sharding

Tests are automatically sharded across 4 parallel CI runners:

```bash
# Run specific shard locally (for debugging CI issues)
inv test.playwright.headless --args="--shard=1/4"
inv test.playwright.headless --args="--shard=2/4"
inv test.playwright.headless --args="--shard=3/4"
inv test.playwright.headless --args="--shard=4/4"
```

### Projects

The Playwright config defines three projects:

| Project | Purpose | Parallelism |
|---------|---------|-------------|
| `chromium` | General E2E tests | Fully parallel |
| `mobile-chrome` | Mobile viewport tests | Fully parallel |
| `herodraft` | Multi-browser draft scenarios | Sequential |

## Authentication

### Fixtures

Tests use custom fixtures for authentication:

```typescript
import { test, expect } from '../../fixtures';

test('admin can edit tournament', async ({ page, loginAdmin }) => {
  await loginAdmin();
  await page.goto('/tournament/1');
  // ... test admin functionality
});

test('staff can view stats', async ({ page, loginStaff }) => {
  await loginStaff();
  // ...
});

test('user can view tournament', async ({ page, loginUser }) => {
  await loginUser();
  // ...
});
```

### Login As Specific User

```typescript
test('captain can make picks', async ({ page, loginAsUser }) => {
  // Login as user with PK 42
  await loginAsUser(42);
  await page.goto('/tournament/1');
  // ...
});
```

### Login By Discord ID

```typescript
test('specific captain flow', async ({ context, loginAsDiscordId }) => {
  await loginAsDiscordId(context, '584468301988757504');
  // ...
});
```

## Page Objects

### TournamentPage

```typescript
import { TournamentPage, getTournamentByKey } from '../../fixtures';

test('tournament page loads', async ({ page, context }) => {
  const tournament = await getTournamentByKey(context, 'completed_bracket');
  const tournamentPage = new TournamentPage(page);

  await tournamentPage.goto(tournament.pk);
  await tournamentPage.clickTeamsTab();
  await tournamentPage.waitForTeamsToLoad();
});
```

### LeaguePage

```typescript
import { LeaguePage, getFirstLeague } from '../../fixtures';

test('league tabs work', async ({ page, context }) => {
  const league = await getFirstLeague(context);
  const leaguePage = new LeaguePage(page);

  await leaguePage.goto(league.pk, 'info');
  await leaguePage.clickTournamentsTab();
  await leaguePage.assertTabActive('tournaments');
});
```

### HeroDraftPage

```typescript
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

test('draft flow', async ({ page }) => {
  const draftPage = new HeroDraftPage(page);

  await draftPage.waitForModal();
  await draftPage.assertWaitingPhase();
  await draftPage.clickReady();
  await draftPage.waitForPhaseTransition('rolling');
});
```

## Test Data

### Tournament Lookup

Tests should use key-based lookup instead of hardcoded IDs:

```typescript
// Good - dynamic lookup
const tournament = await getTournamentByKey(context, 'completed_bracket');
await page.goto(`/tournament/${tournament.pk}`);

// Bad - hardcoded ID
await page.goto('/tournament/1');
```

Available tournament keys (see [Test Tournaments](test-tournaments.md)):

- `completed_bracket` - Fully completed tournament with bracket
- `partial_bracket` - Tournament with some bracket games
- `pending_bracket` - Tournament with no bracket games
- `draft_captain_turn` - Draft waiting for captain pick
- `shuffle_draft_captain_turn` - Shuffle draft waiting for captain

### League Lookup

```typescript
// Get first available league
const league = await getFirstLeague(context);
await leaguePage.goto(league.pk, 'info');
```

## Writing Tests

### Best Practices

```typescript
import { test, expect, visitAndWaitForHydration } from '../../fixtures';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should do something', async ({ page }) => {
    // Use helper for navigation with hydration wait
    await visitAndWaitForHydration(page, '/tournaments');

    // Prefer semantic locators
    await page.getByRole('button', { name: 'Create' }).click();

    // Use data-testid for custom elements
    await page.locator('[data-testid="tournament-name"]').fill('Test');

    // Explicit waits instead of arbitrary timeouts
    await page.waitForLoadState('networkidle');

    // Assertions
    await expect(page.getByText('Success')).toBeVisible();
  });
});
```

### Locator Priority

1. `page.getByRole()` - Accessibility-based (preferred)
2. `page.getByTestId()` - Explicit test hooks
3. `page.getByText()` - Visible text content
4. `page.locator()` - CSS/XPath fallback

### Avoid Arbitrary Waits

```typescript
// Bad - arbitrary timeout
await page.waitForTimeout(2000);

// Good - explicit wait for condition
await page.waitForLoadState('networkidle');
await expect(dialog).toBeVisible();
await page.waitForSelector('[data-testid="loaded"]');
```

## Debugging

### View Test Report

```bash
# Open HTML report after test run
inv test.playwright.report
```

### Trace Viewer

Failed tests automatically capture traces. View them:

```bash
npx playwright show-trace frontend/test-results/path-to-trace.zip
```

### Debug Mode

```bash
# Run with Playwright Inspector
inv test.playwright.debug

# Run specific test in debug mode
inv test.playwright.spec --spec navigation --args="--debug"
```

### UI Mode

```bash
# Interactive UI for running and debugging tests
inv test.playwright.ui
```

## CI Integration

### GitHub Actions

Tests run automatically on push/PR with 4-way sharding:

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - run: inv test.playwright.headless --args="--shard=${{ matrix.shard }}/4"
```

### Artifacts

On failure, CI uploads:

- `playwright-report-{shard}` - HTML report per shard
- `playwright-test-results-{shard}` - Screenshots, videos, traces
- `playwright-report-merged` - Combined report from all shards

## Comparison: Playwright vs Cypress

| Feature | Playwright | Cypress |
|---------|------------|---------|
| Parallel execution | Native | Plugin required |
| Multi-browser | Single test file | Separate runs |
| Auto-waiting | Built-in | Built-in |
| Network mocking | `page.route()` | `cy.intercept()` |
| Cross-origin | Supported | Limited |
| Mobile emulation | Native | Plugin required |

## Migrating from Cypress

See the [Cypress to Playwright Migration Plan](../plans/2026-01-23-cypress-to-playwright-migration.md) for details on:

- API mapping (cy.visit → page.goto, etc.)
- Custom command conversion
- Test structure changes
