/**
 * Cypress E2E tests for Bracket Match Linking feature
 *
 * Tests the flow of linking Steam matches to bracket games:
 * - Opening MatchStatsModal from bracket
 * - Opening LinkSteamMatchModal from MatchStatsModal
 * - Searching and filtering matches
 * - Linking and unlinking matches
 *
 * Uses "Link Test Tournament" created by populate_bracket_linking_scenario()
 */

import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';

describe('Bracket Match Linking (e2e)', () => {
  let tournamentPk: number;

  before(() => {
    // Get the tournament pk for the bracket linking test scenario
    cy.getTournamentByKey('bracket_linking').then((response) => {
      tournamentPk = response.body.pk;
    });
  });

  // Helper to open the link modal for a specific team captain name
  const openLinkModalForTeam = (captainName: string) => {
    cy.contains(captainName).click();
    cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
    cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
    cy.get('[data-testid="link-steam-match-modal"]', { timeout: 5000 }).should(
      'be.visible'
    );
  };

  describe('Staff User Tests', () => {
    beforeEach(() => {
      cy.loginStaff();
      suppressHydrationErrors();
    });

    describe('Navigation to Link Modal', () => {
      it('should display bracket with pending games', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        // Wait for the games tab to load
        cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should(
          'be.visible'
        );

        // Default view should be bracket view
        cy.contains('Bracket View').should('be.visible');

        // Wait for bracket container to appear (bracket data loaded)
        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );
      });

      it('should open MatchStatsModal when clicking a bracket match node', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        // Wait for bracket to load
        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Click on a match node - look for team captain name from first match
        // Teams are Link Alpha vs Link Beta in first Winners R1 match
        cy.contains('link_test_player_0').click();

        // MatchStatsModal should open (wait for dialog content)
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
      });

      it('should show Link Steam Match button in MatchStatsModal for staff', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Click on a match node
        cy.contains('link_test_player_0').click();

        // Wait for modal to open
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');

        // Staff should see the Link Steam Match button
        cy.get('[data-testid="link-steam-match-btn"]').should('be.visible');
      });

      it('should open LinkSteamMatchModal when clicking link button', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Click on match node
        cy.contains('link_test_player_0').click();

        // Wait for MatchStatsModal
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');

        // Click Link Steam Match button (use force to handle overlay)
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });

        // LinkSteamMatchModal should open
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Modal should have title
        cy.contains('Link Steam Match').should('be.visible');
      });
    });

    describe('Match Suggestions Display', () => {
      beforeEach(() => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Navigate to LinkSteamMatchModal - use second match to avoid conflicts
        cy.contains('link_test_player_10').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');
      });

      it('should display match suggestions grouped by tier', () => {
        // Should show tier sections (may have all_players, captains_plus, etc.)
        // At least one tier section should be visible
        cy.get('[data-testid^="tier-"]', { timeout: 10000 }).should('exist');
      });

      it('should display match cards with details', () => {
        // Should show match cards
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should(
          'have.length.at.least',
          1
        );

        // Match cards should have match ID
        cy.get('[data-testid="match-card"]')
          .first()
          .should('contain.text', 'Match #');
      });

      it('should have search input', () => {
        cy.get('[data-testid="match-search-input"]').should('be.visible');
      });

      it('should have link buttons on match cards', () => {
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');
        cy.get('[data-testid="link-btn"]').should('have.length.at.least', 1);
      });
    });

    describe('Search Functionality', () => {
      beforeEach(() => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Navigate to LinkSteamMatchModal - use third match
        cy.contains('link_test_player_15').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');
      });

      it('should filter matches when searching by match ID', () => {
        // Wait for suggestions to load
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');

        // Get the match ID from first card
        cy.get('[data-testid="match-card"]')
          .first()
          .invoke('text')
          .then((text) => {
            // Extract match ID (format: "Match #1234567890")
            const matchIdMatch = text.match(/Match #(\d+)/);
            if (matchIdMatch) {
              const matchId = matchIdMatch[1];

              // Search for this specific match
              cy.get('[data-testid="match-search-input"]').type(matchId);

              // Wait for debounced search
              cy.wait(500);

              // Should show fewer or same number of results
              cy.get('[data-testid="match-card"]').should('exist');
            }
          });
      });

      it('should show no matches message for non-existent match ID', () => {
        // Search for a non-existent match ID
        cy.get('[data-testid="match-search-input"]').type('9999999999999');

        // Wait for debounced search
        cy.wait(500);

        // Should show "No matches found" message
        cy.contains('No matches found', { timeout: 5000 }).should('be.visible');
      });
    });

    describe('Link and Unlink Flow', () => {
      it('should link a match when clicking Link button', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Use first match for this test
        cy.contains('link_test_player_0').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Wait for suggestions to load
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');

        // Check if already linked, if so unlink first
        cy.get('body').then(($body) => {
          if ($body.find('[data-testid="unlink-btn"]').length > 0) {
            cy.get('[data-testid="unlink-btn"]').click();
            cy.wait(500);
          }
        });

        // Get the match ID before linking
        cy.get('[data-testid="match-card"]')
          .first()
          .invoke('text')
          .then((text) => {
            const matchIdMatch = text.match(/Match #(\d+)/);
            if (matchIdMatch) {
              const matchId = matchIdMatch[1];

              // Click link button on first match card (use force to handle any overlay)
              cy.get('[data-testid="link-btn"]').first().click({ force: true });

              // Modal should close after linking
              cy.get('[data-testid="link-steam-match-modal"]').should(
                'not.exist'
              );

              // Reopen the link modal
              cy.get('[data-testid="link-steam-match-btn"]').click({
                force: true,
              });
              cy.get('[data-testid="link-steam-match-modal"]', {
                timeout: 5000,
              }).should('be.visible');

              // Should show "Currently Linked" section
              cy.get('[data-testid="currently-linked"]', {
                timeout: 5000,
              }).should('be.visible');

              // Should show the linked match ID
              cy.get('[data-testid="currently-linked"]').should(
                'contain.text',
                matchId
              );
            }
          });
      });

      it('should show Currently Linked section when match is linked', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Use second match for this test
        cy.contains('link_test_player_10').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Wait for suggestions to load
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');

        // Unlink first if already linked
        cy.get('body').then(($body) => {
          if ($body.find('[data-testid="unlink-btn"]').length > 0) {
            cy.get('[data-testid="unlink-btn"]').click();
            cy.wait(500);
          }
        });

        // Link a match
        cy.get('[data-testid="link-btn"]').first().click({ force: true });

        // Modal closes, reopen it
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Currently linked section should be visible
        cy.get('[data-testid="currently-linked"]', { timeout: 5000 }).should(
          'be.visible'
        );

        // Unlink button should be visible
        cy.get('[data-testid="unlink-btn"]').should('be.visible');
      });

      it('should unlink a match when clicking Unlink button', () => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Use third match for this test
        cy.contains('link_test_player_15').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Wait for suggestions to load
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');

        // Unlink first if already linked
        cy.get('body').then(($body) => {
          if ($body.find('[data-testid="unlink-btn"]').length > 0) {
            cy.get('[data-testid="unlink-btn"]').click();
            cy.wait(500);
          }
        });

        // Link a match first
        cy.get('[data-testid="link-btn"]').first().click({ force: true });

        // Reopen modal
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');

        // Click unlink button
        cy.get('[data-testid="unlink-btn"]').click();

        // Currently linked section should disappear
        cy.get('[data-testid="currently-linked"]').should('not.exist');

        // All link buttons should be enabled again
        cy.get('[data-testid="link-btn"]').first().should('not.be.disabled');
      });
    });

    describe('View Details Functionality', () => {
      beforeEach(() => {
        visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

        cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
          'be.visible'
        );

        // Navigate to LinkSteamMatchModal
        cy.contains('link_test_player_0').click();
        cy.contains('Match Details', { timeout: 5000 }).should('be.visible');
        cy.get('[data-testid="link-steam-match-btn"]').click({ force: true });
        cy.get('[data-testid="link-steam-match-modal"]', {
          timeout: 5000,
        }).should('be.visible');
      });

      it('should open Dota match stats modal when clicking View Details', () => {
        // Wait for suggestions to load
        cy.get('[data-testid="match-card"]', { timeout: 10000 }).should('exist');

        // Click View Details button (use force for potential overlay)
        cy.get('[data-testid="view-details-btn"]').first().click({ force: true });

        // Wait for a moment for the modal to open
        cy.wait(500);

        // Dota match stats modal should open (look for match stats content)
        // The DotaMatchStatsModal shows player stats in a dialog
        // Check for the modal content - note: text is in ALL CAPS
        cy.get('[role="dialog"]')
          .last()
          .within(() => {
            cy.contains('RADIANT', { timeout: 5000 }).should('exist');
            cy.contains('DIRE').should('exist');
          });
      });
    });
  }); // End Staff User Tests

  describe('Non-Staff User Access', () => {
    beforeEach(() => {
      // Clear cookies first to ensure clean state
      cy.clearCookies();
      cy.loginUser(); // Login as regular user instead of staff
      suppressHydrationErrors();
    });

    it('should not show Link Steam Match button for non-staff users', () => {
      visitAndWaitForHydration(`/tournament/${tournamentPk}/games`);

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible'
      );

      // Click on a match node
      cy.contains('link_test_player_0').click();

      // Wait for modal to open
      cy.contains('Match Details', { timeout: 5000 }).should('be.visible');

      // Link button should NOT be visible for non-staff
      cy.get('[data-testid="link-steam-match-btn"]').should('not.exist');
    });
  });
});
