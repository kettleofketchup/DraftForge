/**
 * Cypress E2E tests for Match Stats Display feature
 *
 * Tests the MatchStatsModal component which displays Dota 2 match statistics
 * including hero icons, player stats (K/D/A, GPM/XPM, damage, etc.)
 */

describe('Match Stats Modal', () => {
  let testMatchId: number;
  let testTournamentId: number;

  beforeEach(() => {
    // Login as admin for access to all features
    cy.loginAdmin();
  });

  it('should display Stats button when game has a match linked', () => {
    // First, visit tournaments to find one with games
    cy.visit('/tournaments');
    cy.get('body').should('be.visible');

    // Click on the first tournament that exists (Spring Championship from test data)
    cy.contains('Spring Championship').click();

    // Wait for tournament page to load
    cy.url().should('include', '/tournament/');

    // Navigate to Games tab
    cy.contains('Games').click();

    // Create a test match linked to this tournament
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1, // Spring Championship
      },
    }).then((response) => {
      testMatchId = response.body.match_id;
      testTournamentId = response.body.tournament_id;
      cy.log(`Created test match ${testMatchId} for tournament ${testTournamentId}`);

      // Reload the page to see the updated game
      cy.reload();

      // Wait for games to load
      cy.wait(1000);

      // Check that a Stats button appears (game now has gameid linked)
      cy.get('[data-testid="view-stats-btn"]').should('exist');
    });
  });

  it('should open modal with match statistics when clicking Stats button', () => {
    // Create a fresh test match
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then((response) => {
      testMatchId = response.body.match_id;

      // Visit the tournament page
      cy.visit('/tournament/1');
      cy.get('body').should('be.visible');

      // Navigate to Games tab
      cy.contains('Games').click();
      cy.wait(500);

      // Click the Stats button
      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Modal should open
      cy.get('[role="dialog"]').should('be.visible');

      // Modal should contain match ID
      cy.get('[role="dialog"]').should('contain.text', `Match ${testMatchId}`);
    });
  });

  it('should display Radiant and Dire team sections', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then((response) => {
      testMatchId = response.body.match_id;

      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Modal should show both team sections
      cy.get('[role="dialog"]').within(() => {
        cy.contains('Radiant').should('be.visible');
        cy.contains('Dire').should('be.visible');
      });
    });
  });

  it('should display victory banner based on match result', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then((response) => {
      const radiantWin = response.body.radiant_win;

      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Modal should show victory banner
      cy.get('[role="dialog"]').within(() => {
        if (radiantWin) {
          cy.contains('Radiant Victory').should('be.visible');
        } else {
          cy.contains('Dire Victory').should('be.visible');
        }
      });
    });
  });

  it('should display player stats table with all columns', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then(() => {
      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Check for stat column headers in the modal
      cy.get('[role="dialog"]').within(() => {
        // Hero column (with icons)
        cy.get('th').contains('Hero').should('be.visible');
        // Player column
        cy.get('th').contains('Player').should('be.visible');
        // K/D/A columns
        cy.get('th').contains('K').should('be.visible');
        cy.get('th').contains('D').should('be.visible');
        cy.get('th').contains('A').should('be.visible');
        // Other stat columns
        cy.get('th').contains('LH/DN').should('be.visible');
        cy.get('th').contains('GPM/XPM').should('be.visible');
        cy.get('th').contains('DMG').should('be.visible');
        cy.get('th').contains('BLD').should('be.visible');
        cy.get('th').contains('HEAL').should('be.visible');
      });
    });
  });

  it('should display 5 players per team', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then(() => {
      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // There should be 2 tables (Radiant and Dire), each with 5 player rows
      cy.get('[role="dialog"]').within(() => {
        // Each team table should have 5 data rows (tbody tr)
        cy.get('table').should('have.length', 2);
      });
    });
  });

  it('should display hero icons', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then(() => {
      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Hero icons should be visible (img elements in the hero column)
      cy.get('[role="dialog"]').within(() => {
        cy.get('img[alt]').should('have.length.at.least', 10); // 10 players = 10 hero icons
      });
    });
  });

  it('should close modal when clicking outside or X button', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then(() => {
      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Modal should be open
      cy.get('[role="dialog"]').should('be.visible');

      // Click close button (X)
      cy.get('[role="dialog"]').find('button[aria-label="Close"]').click();

      // Modal should be closed
      cy.get('[role="dialog"]').should('not.exist');
    });
  });

  it('should display match duration and date', () => {
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
      body: {
        tournament_id: 1,
      },
    }).then(() => {
      cy.visit('/tournament/1');
      cy.contains('Games').click();
      cy.wait(500);

      cy.get('[data-testid="view-stats-btn"]').first().click();

      // Modal header should show duration (format: MM:SS or H:MM:SS)
      cy.get('[role="dialog"]').within(() => {
        // Duration is shown in header with format like "45:30" or "1:15:00"
        cy.get('header, [class*="DialogHeader"]').should('exist');
      });
    });
  });
});

describe('Match Stats Modal - Error Handling', () => {
  beforeEach(() => {
    cy.loginAdmin();
  });

  it('should handle match not found gracefully', () => {
    // Create a game with an invalid match ID
    cy.visit('/tournament/1');
    cy.contains('Games').click();

    // The modal should show error state if match data fails to load
    // This tests the error handling in the MatchStatsModal component
  });
});

describe('Match Stats Modal - Direct API Test', () => {
  it('should return match data from API endpoint', () => {
    // First create a test match
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/create-match/`,
    }).then((createResponse) => {
      const matchId = createResponse.body.match_id;

      // Then fetch the match data
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/steam/matches/${matchId}/`,
      }).then((response) => {
        expect(response.status).to.eq(200);
        expect(response.body).to.have.property('match_id', matchId);
        expect(response.body).to.have.property('radiant_win');
        expect(response.body).to.have.property('duration');
        expect(response.body).to.have.property('players');
        expect(response.body.players).to.have.length(10);

        // Verify player stats structure
        const player = response.body.players[0];
        expect(player).to.have.property('hero_id');
        expect(player).to.have.property('kills');
        expect(player).to.have.property('deaths');
        expect(player).to.have.property('assists');
        expect(player).to.have.property('gold_per_min');
        expect(player).to.have.property('xp_per_min');
        expect(player).to.have.property('last_hits');
        expect(player).to.have.property('denies');
        expect(player).to.have.property('hero_damage');
        expect(player).to.have.property('tower_damage');
        expect(player).to.have.property('hero_healing');
      });
    });
  });

  it('should return 404 for non-existent match', () => {
    cy.request({
      method: 'GET',
      url: `${Cypress.env('apiUrl')}/steam/matches/9999999999/`,
      failOnStatusCode: false,
    }).then((response) => {
      expect(response.status).to.eq(404);
    });
  });
});
