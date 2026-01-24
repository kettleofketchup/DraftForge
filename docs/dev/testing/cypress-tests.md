# Cypress E2E Testing Guide

Comprehensive documentation for the Cypress end-to-end test suite for DraftForge.

## Overview

The test suite validates user-facing functionality through browser automation. Tests run against the test Docker environment with a populated database.

## Test Structure

```
frontend/tests/cypress/
├── e2e/                          # Test specs organized by feature
│   ├── 00-hydration-handling.cy.ts
│   ├── 01-navigation.cy.ts
│   ├── 03-tournaments/           # Tournament list page
│   │   ├── 01-page.cy.ts
│   │   ├── 02-form.cy.ts
│   │   └── constants.ts
│   ├── 04-tournament/            # Single tournament page
│   │   ├── 01-page.cy.ts
│   │   ├── 02-user.cy.ts
│   │   ├── 03-ui-elements.cy.ts
│   │   └── constants.ts
│   ├── 05-match-stats/
│   │   └── 01-modal.cy.ts
│   ├── 06-mobile/
│   │   └── 01-responsive.cy.ts
│   ├── 07-draft/                 # Captain draft tests
│   │   ├── 01-captain-pick.cy.ts
│   │   ├── 02-undo-pick.cy.ts
│   │   └── constants.ts
│   ├── 08-shuffle-draft/
│   │   ├── 01-full-draft.cy.ts
│   │   └── 02-roll.cy.ts
│   ├── 09-bracket/
│   │   ├── 01-bracket-badges.cy.ts
│   │   ├── 02-bracket-match-linking.cy.ts
│   │   └── 03-bracket-winner-advancement.cy.ts
│   └── 10-leagues/
│       ├── 01-tabs.cy.ts
│       ├── 02-edit-modal.cy.ts
│       ├── 03-matches.cy.ts
│       └── constants.ts
├── fixtures/                     # Test data
│   ├── auth.json
│   └── testData.json
├── helpers/                      # Reusable test utilities
│   ├── types.d.ts               # TypeScript types
│   ├── users.ts                 # User interaction helpers
│   ├── draft.ts                 # Draft modal helpers
│   ├── tournament.ts            # Tournament helpers
│   └── league.ts                # League helpers
└── support/
    ├── commands.ts              # Custom Cypress commands
    ├── e2e.ts                   # Global test setup
    ├── utils.ts                 # Utility functions
    └── component.ts             # Component test setup
```

## Test Categories

### Navigation & Hydration (00-01)

**Purpose**: Validate React hydration and basic navigation work correctly.

- `00-hydration-handling.cy.ts` - Tests React hydration handling
- `01-navigation.cy.ts` - Tests site navigation and routing

### Tournaments (03-04)

**Purpose**: Validate tournament listing and detail pages.

- `03-tournaments/` - Tournament list page (creating, filtering)
- `04-tournament/` - Single tournament page (viewing, user interactions, UI elements)

### Match Stats (05)

**Purpose**: Validate match statistics modal and data display.

### Mobile/Responsive (06)

**Purpose**: Validate responsive behavior on mobile viewports.

### Draft System (07-08)

**Purpose**: Validate the captain draft and shuffle draft systems.

- `07-draft/` - Captain pick flow, undo functionality, notifications
- `08-shuffle-draft/` - Full draft flow, roll mechanics

### Bracket System (09)

**Purpose**: Validate bracket display and match management.

- Bracket badges and visual indicators
- Match linking between winners/losers brackets
- Winner advancement logic

### Leagues (10)

**Purpose**: Validate league page functionality.

- Tab navigation
- Edit modal
- Matches display

## Running Tests

### Prerequisites

Ensure the test environment is running:

```bash
source .venv/bin/activate
inv test.setup     # Full setup (builds, migrates, populates, starts)
```

Or if the environment is already set up:

```bash
inv dev.test       # Start test environment
inv db.populate.all  # Populate test data
```

### Interactive Mode (Recommended for Development)

Opens the Cypress Test Runner GUI:

```bash
inv test.open
```

### Headless Mode (CI/CD)

Runs all tests in headless mode:

```bash
inv test.headless
```

### Run Specific Test Categories

```bash
# By category
inv test.cypress.draft       # Draft tests (07-draft, 08-shuffle-draft)
inv test.cypress.tournament  # Tournament tests (03, 04)
inv test.cypress.bracket     # Bracket tests (09)
inv test.cypress.league      # League tests (10)
inv test.cypress.navigation  # Navigation tests (00, 01)
inv test.cypress.mobile      # Mobile tests (06)
inv test.cypress.all         # All Cypress tests

# By spec pattern
inv test.spec --spec drafts      # 07-draft/**/*.cy.ts
inv test.spec --spec tournament  # 04-tournament/**/*.cy.ts
inv test.spec --spec 01          # 01-*.cy.ts
```

### Parallel Execution

```bash
inv test.parallel            # Run with 3 threads (default)
inv test.parallel --threads 4  # Custom thread count
```

## Writing New Tests

### File Naming Convention

Tests are numbered for execution order:

```
XX-feature-name/
  YY-aspect.cy.ts
```

- `XX` = Feature category number (00-99)
- `YY` = Test file number within category

### Test Structure Template

```typescript
import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';
import { helperFunction } from 'tests/cypress/helpers/feature';

describe('Feature Name (e2e)', () => {
  beforeEach(() => {
    // Suppress React hydration warnings
    suppressHydrationErrors();

    // Login as appropriate user
    cy.loginAdmin();  // or cy.loginStaff() or cy.loginUser()
  });

  it('should do something specific', () => {
    visitAndWaitForHydration('/page-url');

    // Test assertions
    cy.get('[data-testid="element"]').should('be.visible');
  });
});
```

### Element Selection Best Practices

**Always use `data-testid` attributes**:

```typescript
// Good
cy.get('[data-testid="submit-button"]').click();

// Avoid
cy.get('.submit-btn').click();  // Fragile - class might change
cy.get('button').contains('Submit').click();  // Slower, less specific
```

### Authentication

Use custom commands for authentication:

```typescript
cy.loginAdmin();   // Login as admin user
cy.loginStaff();   // Login as staff user
cy.loginUser();    // Login as regular user
cy.loginAsUser(pk);  // Login as specific user by primary key
```

### Handling Hydration

Always wait for hydration before interacting:

```typescript
import { visitAndWaitForHydration } from 'tests/cypress/support/utils';

// Good
visitAndWaitForHydration('/tournaments');
cy.get('[data-testid="element"]').click();

// Alternative using custom command
cy.visitAndWaitForReact('/tournaments');
```

### Getting Test Data

Use the test API endpoints to get dynamic data:

```typescript
// Get tournament by test config key
cy.getTournamentByKey('draft_captain_turn').then((response) => {
  const tournamentPk = response.body.pk;
  // Use tournamentPk in tests
});
```

## Test Helpers

### Support Utils (`support/utils.ts`)

| Function | Description |
|----------|-------------|
| `visitAndWaitForHydration(url)` | Navigate and wait for React hydration |
| `suppressHydrationErrors()` | Suppress React hydration warnings |
| `waitForLoadingToComplete()` | Wait for loading indicators to disappear |
| `navigateToRoute(route)` | Smart navigation handling dropdowns |
| `checkBasicAccessibility()` | Basic a11y checks |

### Custom Commands (`support/commands.ts`)

| Command | Description |
|---------|-------------|
| `cy.loginAdmin()` | Login as admin via API |
| `cy.loginStaff()` | Login as staff via API |
| `cy.loginUser()` | Login as regular user via API |
| `cy.loginAsUser(pk)` | Login as specific user by PK |
| `cy.getTournamentByKey(key)` | Get tournament by test config key |
| `cy.logout()` | Logout current user |
| `cy.waitForHydration()` | Wait for React hydration |
| `cy.visitAndWaitForReact(url)` | Visit and wait for React |
| `cy.isInViewport()` | Check if element is in viewport |

### Draft Helpers (`helpers/draft.ts`)

| Function | Description |
|----------|-------------|
| `waitForUserLoggedIn(cy)` | Wait for user avatar to appear |
| `getDraftButton(cy)` | Get draft modal trigger button |
| `openDraftModal(cy)` | Navigate to Teams tab and open draft |
| `getAvailablePlayer(cy, username)` | Get available player row |
| `pickPlayer(cy, username)` | Pick a player and confirm |
| `assertMyTurn(cy)` | Assert it's current user's turn |
| `getFloatingDraftIndicator(cy)` | Get floating draft notification |
| `visitTournamentWithDraftOpen(cy, pk)` | Visit with `?draft=open` |

### Tournament Helpers (`helpers/tournament.ts`)

| Function | Description |
|----------|-------------|
| `addPlayerToTournament(cy, username)` | Add player via UI |
| `openCreateTournamentModal(cy)` | Open tournament creation modal |
| `fillTournamentForm(cy, options)` | Fill tournament form fields |
| `createTournament(cy, options)` | Complete tournament creation flow |

### League Helpers (`helpers/league.ts`)

| Function | Description |
|----------|-------------|
| `getInfoTab(cy)` | Get Info tab element |
| `getTournamentsTab(cy)` | Get Tournaments tab element |
| `getMatchesTab(cy)` | Get Matches tab element |
| `visitLeaguePage(cy, id, tab)` | Visit league page with tab |
| `openEditModal(cy)` | Open league edit modal |
| `fillEditForm(cy, options)` | Fill league edit form |

### User Helpers (`helpers/users.ts`)

| Function | Description |
|----------|-------------|
| `getUserCard(cy, username)` | Get user card by username |
| `getUserRemoveButton(cy, username)` | Get remove button for user |

## Test Data Requirements

Tests depend on pre-populated test data. Key test configurations:

- `draft_captain_turn` - Tournament with active draft, captain ready to pick
- Tournament IDs 1, 2, 3 - Various bracket states (completed, partial, pending)
- League with ID from `TEST_LEAGUE_ID` constant

Populate test data with:

```bash
inv db.populate.all
```

## Debugging Tips

### Visual Debugging

1. Run in interactive mode: `inv test.open`
2. Use time-travel debugging in Cypress UI
3. Add `cy.pause()` to stop execution at a point

### Console Logging

```typescript
cy.log('Debug message');
cy.get('[data-testid="element"]').then($el => {
  console.log('Element:', $el);
});
```

### Screenshots

Cypress automatically captures screenshots on failure. Manual capture:

```typescript
cy.screenshot('descriptive-name');
```

### Common Issues

**React Hydration Warnings**: Use `suppressHydrationErrors()` in `beforeEach`

**Element Not Found**: Ensure proper wait for hydration and check timeouts

**Flaky Tests**: Avoid `cy.wait(ms)` when possible, use assertions instead

**State Pollution**: Clear storage in `beforeEach`:

```typescript
beforeEach(() => {
  cy.clearCookies();
  cy.clearLocalStorage();
  cy.window().then((win) => win.sessionStorage.clear());
});
```

## CI/CD Integration

Tests run automatically via invoke tasks:

```bash
# Full CI/CD test suite
inv test.cicd.all      # Backend + Cypress

# Individual suites
inv test.cicd.cypress  # Cypress only (with setup)
inv test.cicd.backend  # Backend only
```

The CI pipeline:

1. Builds Docker images
2. Runs database migrations
3. Populates test data
4. Executes tests
5. Reports results

## Adding Test IDs to Components

When adding new UI features, include `data-testid` attributes:

```tsx
// Component
<Button data-testid="submit-draft-pick">Pick Player</Button>

// Test
cy.get('[data-testid="submit-draft-pick"]').click();
```

Naming conventions:

- Use kebab-case: `data-testid="user-profile-card"`
- Include context: `data-testid="tournament-name-input"`
- For dynamic elements: `data-testid={`player-card-${player.id}`}`
