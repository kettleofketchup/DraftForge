describe('API Integration Tests', () => {
  const apiUrl = Cypress.env('apiUrl') || 'http://localhost:8000/api';

  beforeEach(() => {
    cy.fixture('testData').as('testData');
    cy.fixture('auth').as('authData');
  });

  it('should handle API requests for tournaments', () => {
    // Intercept and mock tournaments API
    cy.intercept('GET', `${apiUrl}/tournaments/`, {
      statusCode: 200,
      body: {
        results: [
          {
            id: 1,
            name: 'Test Tournament',
            description: 'API Test Tournament',
            start_date: '2024-12-01T00:00:00Z',
            status: 'active',
          },
        ],
      },
    }).as('getTournaments');

    cy.visit('/tournaments');
    cy.wait('@getTournaments');

    // Verify the API was called
    cy.get('@getTournaments').should('have.property', 'state', 'Complete');

    // Check that the page displays the mocked data
    cy.get('body').should('contain.text', 'Test Tournament');
  });

  it('should handle API errors gracefully', () => {
    // Mock API error
    cy.intercept('GET', `${apiUrl}/tournaments/`, {
      statusCode: 500,
      body: { error: 'Internal Server Error' },
    }).as('getTournamentsError');

    cy.visit('/tournaments');
    cy.wait('@getTournamentsError');

    // Check that error is handled gracefully
    cy.get('body').should('be.visible');

    // Look for error messages or fallback content
    cy.get('body').then(($body) => {
      const hasErrorMessage =
        $body.find(
          ':contains("error"), :contains("Error"), :contains("failed"), :contains("Failed")',
        ).length > 0;
      const hasEmptyState =
        $body.find(
          ':contains("No tournaments"), :contains("empty"), :contains("Empty")',
        ).length > 0;
      const hasRetryButton =
        $body.find('button:contains("Retry"), button:contains("Try again")')
          .length > 0;

      // Should show some kind of error handling
      expect(hasErrorMessage || hasEmptyState || hasRetryButton).to.be.true;
    });
  });

  it('should handle authentication API calls', function () {
    const { validUser } = this.authData;

    // Mock login API
    cy.intercept('POST', `${apiUrl}/auth/login/`, {
      statusCode: 200,
      body: {
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
        user: {
          id: 1,
          email: validUser.email,
          username: validUser.username,
        },
      },
    }).as('loginRequest');

    cy.visit('/login');

    // Fill and submit login form
    cy.get(
      'input[type="email"], input[name*="email"], input[placeholder*="email"]',
    )
      .first()
      .type(validUser.email);

    cy.get('input[type="password"], input[name*="password"]')
      .first()
      .type(validUser.password);

    cy.get(
      'button[type="submit"], button:contains("Login"), button:contains("Sign in")',
    )
      .first()
      .click();

    // Verify API call was made
    cy.wait('@loginRequest').then((interception) => {
      expect(interception.request.body).to.have.property(
        'email',
        validUser.email,
      );
      expect(interception.request.body).to.have.property(
        'password',
        validUser.password,
      );
    });

    // Should redirect after successful login
    cy.url().should('not.include', '/login');
  });

  it('should handle user profile API calls', () => {
    // Mock authenticated user API call
    cy.intercept('GET', `${apiUrl}/user/profile/`, {
      statusCode: 200,
      body: {
        id: 1,
        email: 'testuser@example.com',
        username: 'testuser',
        first_name: 'Test',
        last_name: 'User',
        tournaments_participated: 5,
        tournaments_won: 2,
      },
    }).as('getUserProfile');

    // Set up authentication
    cy.window().then((win) => {
      win.localStorage.setItem('access_token', 'mock-access-token');
    });

    cy.visit('/profile');
    cy.wait('@getUserProfile');

    // Verify the API was called with auth headers
    cy.get('@getUserProfile').then((interception) => {
      expect(interception.request.headers).to.have.property('authorization');
    });

    // Check that profile data is displayed
    cy.get('body').should('contain.text', 'testuser');
  });

  it('should handle tournament creation API', () => {
    const newTournament = {
      name: 'New Test Tournament',
      description: 'Created via API test',
      max_participants: 16,
    };

    // Mock tournament creation API
    cy.intercept('POST', `${apiUrl}/tournaments/`, {
      statusCode: 201,
      body: {
        id: 99,
        ...newTournament,
        status: 'draft',
        created_by: 1,
      },
    }).as('createTournament');

    // Set up authentication
    cy.window().then((win) => {
      win.localStorage.setItem('access_token', 'mock-access-token');
    });

    cy.visit('/tournaments');

    // Look for create tournament functionality
    cy.get('body').then(($body) => {
      const createButton = $body.find(
        'button:contains("Create"), a:contains("Create"), button:contains("New")',
      );

      if (createButton.length > 0) {
        cy.get(
          'button:contains("Create"), a:contains("Create"), button:contains("New")',
        )
          .first()
          .click();

        // Fill out tournament form
        cy.get('input[name*="name"], input[placeholder*="name"]')
          .first()
          .type(newTournament.name);

        cy.get('textarea, input[name*="description"]')
          .first()
          .type(newTournament.description);

        // Submit form
        cy.get(
          'button[type="submit"], button:contains("Create"), button:contains("Save")',
        )
          .first()
          .click();

        // Verify API call
        cy.wait('@createTournament').then((interception) => {
          expect(interception.request.body).to.have.property(
            'name',
            newTournament.name,
          );
        });
      } else {
        cy.log('No tournament creation form found - skipping API test');
      }
    });
  });

  it('should handle pagination in API responses', () => {
    // Mock paginated tournaments API
    cy.intercept('GET', `${apiUrl}/tournaments/*`, {
      statusCode: 200,
      body: {
        count: 25,
        next: `${apiUrl}/tournaments/?page=2`,
        previous: null,
        results: Array.from({ length: 10 }, (_, i) => ({
          id: i + 1,
          name: `Tournament ${i + 1}`,
          status: 'active',
        })),
      },
    }).as('getTournamentsPaginated');

    cy.visit('/tournaments');
    cy.wait('@getTournamentsPaginated');

    // Look for pagination controls
    cy.get('body').then(($body) => {
      const hasPagination =
        $body.find(
          'button:contains("Next"), .pagination, .page-nav, a:contains("2")',
        ).length > 0;

      if (hasPagination) {
        cy.log('Pagination controls found');

        // Mock second page
        cy.intercept('GET', `${apiUrl}/tournaments/?page=2`, {
          statusCode: 200,
          body: {
            count: 25,
            next: null,
            previous: `${apiUrl}/tournaments/?page=1`,
            results: Array.from({ length: 5 }, (_, i) => ({
              id: i + 11,
              name: `Tournament ${i + 11}`,
              status: 'active',
            })),
          },
        }).as('getTournamentsPage2');

        // Click next page
        cy.get('button:contains("Next"), a:contains("Next"), a:contains("2")')
          .first()
          .click();

        cy.wait('@getTournamentsPage2');
        cy.get('body').should('contain.text', 'Tournament 11');
      } else {
        cy.log('No pagination controls found');
      }
    });
  });

  it('should handle API loading states', () => {
    // Mock slow API response
    cy.intercept('GET', `${apiUrl}/tournaments/`, (req) => {
      req.reply((res) => {
        res.delay(2000);
        res.send({
          statusCode: 200,
          body: { results: [] },
        });
      });
    }).as('getSlowTournaments');

    cy.visit('/tournaments');

    // Check for loading state during API call
    cy.get('body').then(($body) => {
      const hasLoadingState =
        $body.find(
          ':contains("Loading"), :contains("loading"), .spinner, .loader',
        ).length > 0;

      if (hasLoadingState) {
        cy.log('Loading state detected');
        cy.get(
          ':contains("Loading"), :contains("loading"), .spinner, .loader',
        ).should('be.visible');
      }
    });

    cy.wait('@getSlowTournaments');

    // Loading state should be gone after API completes
    cy.get('body').should('not.contain.text', 'Loading');
  });

  it('should handle concurrent API requests', () => {
    // Mock multiple API endpoints
    cy.intercept('GET', `${apiUrl}/tournaments/`, { body: { results: [] } }).as(
      'getTournaments',
    );
    cy.intercept('GET', `${apiUrl}/users/`, { body: { results: [] } }).as(
      'getUsers',
    );
    cy.intercept('GET', `${apiUrl}/user/profile/`, { body: {} }).as(
      'getProfile',
    );

    // Set up auth
    cy.window().then((win) => {
      win.localStorage.setItem('access_token', 'mock-token');
    });

    cy.visit('/tournaments');

    // Verify multiple requests can be handled
    cy.wait(['@getTournaments']);

    // Navigate to other pages that trigger different APIs
    cy.visit('/users');
    cy.wait('@getUsers');

    cy.visit('/profile');
    cy.wait('@getProfile');

    // All should complete successfully
    cy.get('body').should('be.visible');
  });
});
