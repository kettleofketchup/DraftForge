# Tournament Cypress Test Identifiers

This document lists all the test identifiers added to tournament components for Cypress testing.

## Tournament Detail Page
- `tournamentDetailPage` - Main tournament detail page container
- `tournamentTitle` - Tournament title heading

## Tournament Tabs
- `tournamentTabsList` - Container for all tab triggers
- `playersTab` - Players tab trigger
- `teamsTab` - Teams tab trigger
- `bracketTab` - Bracket tab trigger
- `playersTabContent` - Players tab content area
- `teamsTabContent` - Teams tab content area
- `bracketTabContent` - Bracket tab content area

## Players Tab
- `playerSearchDropdown` - Main search dropdown for players
- `tournamentAddPlayerBtn` - Button to open add player modal
- `addPlayerCancelBtn` - Cancel button in add player modal
- `playerSearchInput` - Search input in add player dropdown
- `playerOption-{user.username}` - Individual player options (dynamic IDs based on user username)
- `removePlayerBtn-{user.username}` - Remove player buttons (dynamic IDs based on user username)

## Teams Tab
- `teamsSearchDropdown` - Search dropdown for teams
- `createTeamsBtn` - Button to open create teams modal
- `regenerateTeamsBtn` - Button to regenerate team assignments
- `submitTeamsBtn` - Submit button for team creation
- `cancelTeamsCreationBtn` - Cancel button in teams creation dialog
- `confirmTeamsCreationBtn` - Confirm button in teams creation dialog
- `closeTeamsModalBtn` - Close button for teams modal

## Bracket Tab
- `gameCreateModalBtn` - Button to create new game

## Usage Examples

### Basic Navigation
```javascript
// Navigate to tournament and check title
cy.visit('/tournament/123');
cy.get('[data-testid="tournamentDetailPage"]').should('be.visible');
cy.get('[data-testid="tournamentTitle"]').should('contain', 'Tournament Name');

// Switch to teams tab
cy.get('[data-testid="teamsTab"]').click();
cy.get('[data-testid="teamsTabContent"]').should('be.visible');
```

### Adding Players
```javascript
// Open add player modal
cy.get('[data-testid="tournamentAddPlayerBtn"]').click();

// Search for a player
cy.get('[data-testid="playerSearchInput"]').type('player name');

// Select first player option
cy.get('[data-testid^="playerOption-"]').first().click();

// Cancel if needed
cy.get('[data-testid="addPlayerCancelBtn"]').click();
```

### Team Management
```javascript
// Create teams
cy.get('[data-testid="createTeamsBtn"]').click();
cy.get('[data-testid="regenerateTeamsBtn"]').click();
cy.get('[data-testid="submitTeamsBtn"]').click();
cy.get('[data-testid="confirmTeamsCreationBtn"]').click();
```

### Dynamic ID Patterns
For components created in loops that need unique identifiers:
- Player options: `playerOption-{user.username}`
- Remove buttons: `removePlayerBtn-{user.username}`

These allow you to target specific users:
```javascript
// Remove specific player by username
cy.get('[data-testid="removePlayerBtn-kettleofketchup"]').click();

// Select specific player option by username
cy.get('[data-testid="playerOption-johnsmith"]').click();
```
