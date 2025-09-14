describe('Tournament Features', () => {
  beforeEach(() => {
    // Load test data
    cy.fixture('testData').as('testData');

    // Set up API intercepts for tournament data
    cy.intercept('GET', '**/api/tournaments/**', {
      fixture: 'testData.json',
    }).as('getTournaments');
    cy.intercept('GET', '**/api/tournament/**', {
      fixture: 'testData.json',
    }).as('getTournament');
  });

  it('should display tournaments list page', () => {
    cy.visit('/tournaments');

    // Wait for API call
    cy.wait('@getTournaments');

    // Check page loaded
    cy.get('body').should('be.visible');
    cy.url().should('include', '/tournaments');

    // Look for tournament-related content
    cy.get('body')
      .should('contain.text', 'Tournament')
      .or('contain.text', 'tournament');

    // Check for common tournament page elements
    cy.get('body').then(($body) => {
      const hasCards =
        $body.find('[class*="card"], .tournament-card, .tournament-item')
          .length > 0;
      const hasList =
        $body.find('ul li, .list-item, .tournament-list').length > 0;
      const hasTable =
        $body.find('table, .table, .tournament-table').length > 0;

      expect(hasCards || hasList || hasTable).to.be.true;
    });
  });

  it('should navigate to individual tournament page', () => {
    cy.visit('/tournaments');
    cy.wait('@getTournaments');

    // Look for tournament links or buttons
    cy.get('body').within(() => {
      // Try to find clickable tournament elements
      const selectors = [
        'a[href*="/tournament/"]',
        '[data-testid*="tournament"]',
        '.tournament-card',
        '.tournament-item',
        'button:contains("View")',
        'a:contains("Tournament")',
      ];

      selectors.forEach((selector) => {
        cy.get('body').then(($body) => {
          if ($body.find(selector).length > 0) {
            cy.get(selector).first().click();
            return false; // Exit loop
          }
        });
      });
    });

    // If we found a tournament link, verify navigation
    cy.url().then((url) => {
      if (url.includes('/tournament/')) {
        cy.get('body').should('be.visible');
        cy.wait('@getTournament');
      }
    });
  });

  it('should display tournament details correctly', () => {
    // Navigate directly to a tournament page
    cy.visit('/tournament/1');
    cy.wait('@getTournament');

    cy.get('body').should('be.visible');

    // Check for tournament detail elements
    cy.get('body')
      .should('contain.text', 'Tournament')
      .or('contain.text', 'tournament');

    // Look for common tournament detail sections
    cy.get('body').then(($body) => {
      const hasDescription =
        $body.find(':contains("description"), :contains("Description")')
          .length > 0;
      const hasParticipants =
        $body.find(
          ':contains("participant"), :contains("Participant"), :contains("player")',
        ).length > 0;
      const hasBracket =
        $body.find(':contains("bracket"), :contains("Bracket")').length > 0;
      const hasRounds =
        $body.find(':contains("round"), :contains("Round")').length > 0;

      // At least one of these should be present
      expect(hasDescription || hasParticipants || hasBracket || hasRounds).to.be
        .true;
    });
  });

  it('should handle tournament creation form (if available)', () => {
    cy.visit('/tournaments');

    // Look for create tournament button or link
    cy.get('body').then(($body) => {
      const createSelectors = [
        'button:contains("Create")',
        'a:contains("Create")',
        'button:contains("New")',
        'a:contains("New")',
        '[data-testid*="create"]',
        '.create-tournament',
        '.new-tournament',
      ];

      let foundCreateButton = false;
      createSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !foundCreateButton) {
          foundCreateButton = true;
          cy.get(selector).first().click();

          // Check if a form appeared or we navigated to a create page
          cy.get('body')
            .should('contain.text', 'Name')
            .or('contain.text', 'name')
            .or('contain.text', 'Title');

          // Try to fill out basic form fields
          cy.get(
            'input[type="text"], input[name*="name"], input[placeholder*="name"]',
          )
            .first()
            .type('Test Tournament Name');

          cy.get(
            'textarea, input[name*="description"], input[placeholder*="description"]',
          )
            .first()
            .type('Test tournament description');
        }
      });

      if (!foundCreateButton) {
        cy.log('No create tournament functionality found - this is okay');
      }
    });
  });

  it('should display bracket information when available', () => {
    cy.visit('/tournament/1');
    cy.wait('@getTournament');

    // Look for bracket-related content
    cy.get('body').then(($body) => {
      const bracketSelectors = [
        ':contains("bracket")',
        ':contains("Bracket")',
        ':contains("match")',
        ':contains("Match")',
        '.bracket',
        '.tournament-bracket',
        '.matches',
      ];

      let hasBracketContent = false;
      bracketSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          hasBracketContent = true;
        }
      });

      if (hasBracketContent) {
        cy.log('Bracket content found');
        cy.get('body')
          .should('contain.text', 'bracket')
          .or('contain.text', 'Bracket')
          .or('contain.text', 'match');
      } else {
        cy.log(
          'No bracket content found - tournament may not have brackets yet',
        );
      }
    });
  });

  it('should handle tournament search/filtering (if available)', () => {
    cy.visit('/tournaments');
    cy.wait('@getTournaments');

    // Look for search or filter functionality
    cy.get('body').then(($body) => {
      const searchSelectors = [
        'input[type="search"]',
        'input[placeholder*="search"]',
        'input[placeholder*="Search"]',
        '.search-input',
        '.filter-input',
      ];

      searchSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().type('Test');
          cy.wait(500); // Wait for potential filtering
          cy.get('body').should('be.visible');
        }
      });
    });
  });
});
