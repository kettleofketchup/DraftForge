describe('User Authentication and Profile', () => {
  beforeEach(() => {
    // Load auth fixtures
    cy.fixture('auth').as('authData');
  });

  it('should display login page', () => {
    cy.visit('/login');

    cy.get('body').should('be.visible');
    cy.url().should('include', '/login');

    // Check for login form elements
    cy.get('body')
      .should('contain.text', 'Login')
      .or('contain.text', 'login')
      .or('contain.text', 'Sign in');

    // Look for email/username and password fields
    cy.get('body').then(($body) => {
      const hasEmailField =
        $body.find(
          'input[type="email"], input[name*="email"], input[placeholder*="email"]',
        ).length > 0;
      const hasPasswordField =
        $body.find('input[type="password"], input[name*="password"]').length >
        0;
      const hasUsernameField =
        $body.find('input[name*="username"], input[placeholder*="username"]')
          .length > 0;

      expect(hasPasswordField).to.be.true;
      expect(hasEmailField || hasUsernameField).to.be.true;
    });
  });

  it('should handle login form submission', function () {
    cy.visit('/login');

    const { validUser } = this.authData;

    // Fill out login form
    cy.get('body').within(() => {
      // Find and fill email/username field
      cy.get(
        'input[type="email"], input[name*="email"], input[placeholder*="email"]',
      )
        .first()
        .type(validUser.email);

      // Find and fill password field
      cy.get('input[type="password"], input[name*="password"]')
        .first()
        .type(validUser.password);

      // Submit form
      cy.get(
        'button[type="submit"], button:contains("Login"), button:contains("Sign in"), .login-button',
      )
        .first()
        .click();
    });

    // Should redirect away from login page
    cy.url().should('not.include', '/login');
    cy.get('body').should('be.visible');
  });

  it('should handle invalid login credentials', function () {
    cy.visit('/login');

    const { invalidUser } = this.authData;

    // Fill out login form with invalid credentials
    cy.get('body').within(() => {
      cy.get(
        'input[type="email"], input[name*="email"], input[placeholder*="email"]',
      )
        .first()
        .type(invalidUser.email);

      cy.get('input[type="password"], input[name*="password"]')
        .first()
        .type(invalidUser.password);

      cy.get(
        'button[type="submit"], button:contains("Login"), button:contains("Sign in")',
      )
        .first()
        .click();
    });

    // Should show error message or stay on login page
    cy.get('body').then(($body) => {
      const hasErrorMessage =
        $body.find(
          ':contains("error"), :contains("Error"), :contains("invalid"), :contains("Invalid")',
        ).length > 0;
      const staysOnLogin = window.location.pathname.includes('/login');

      expect(hasErrorMessage || staysOnLogin).to.be.true;
    });
  });

  it('should display user profile page when logged in', () => {
    // Mock authentication state
    cy.window().then((win) => {
      win.localStorage.setItem('authToken', 'mock-auth-token');
      win.localStorage.setItem(
        'user',
        JSON.stringify({
          id: 1,
          email: 'testuser@example.com',
          username: 'testuser',
        }),
      );
    });

    cy.visit('/profile');

    cy.get('body').should('be.visible');
    cy.url().should('include', '/profile');

    // Check for profile-related content
    cy.get('body')
      .should('contain.text', 'Profile')
      .or('contain.text', 'profile');

    // Look for user information display
    cy.get('body').then(($body) => {
      const hasUserInfo =
        $body.find(':contains("testuser"), :contains("testuser@example.com")')
          .length > 0;
      const hasProfileFields =
        $body.find('input, .profile-field, .user-info').length > 0;

      expect(hasUserInfo || hasProfileFields).to.be.true;
    });
  });

  it('should display users list page', () => {
    cy.visit('/users');

    cy.get('body').should('be.visible');
    cy.url().should('include', '/users');

    // Check for users-related content
    cy.get('body')
      .should('contain.text', 'Users')
      .or('contain.text', 'users')
      .or('contain.text', 'Members');

    // Look for user list elements
    cy.get('body').then(($body) => {
      const hasUserCards =
        $body.find('[class*="user"], .member-card, .player-card').length > 0;
      const hasUserList = $body.find('ul li, .list-item').length > 0;
      const hasUserTable = $body.find('table, .table').length > 0;

      expect(hasUserCards || hasUserList || hasUserTable).to.be.true;
    });
  });

  it('should navigate to individual user page', () => {
    cy.visit('/users');

    // Look for user profile links
    cy.get('body').then(($body) => {
      const userLinks = $body.find(
        'a[href*="/user/"], [data-testid*="user"], .user-link',
      );

      if (userLinks.length > 0) {
        cy.get('a[href*="/user/"], [data-testid*="user"], .user-link')
          .first()
          .click();

        // Verify navigation to user page
        cy.url().should('include', '/user/');
        cy.get('body').should('be.visible');

        // Check for user profile content
        cy.get('body')
          .should('contain.text', 'Profile')
          .or('contain.text', 'User')
          .or('contain.text', 'Member');
      } else {
        cy.log('No user profile links found');
      }
    });
  });

  it('should handle logout functionality', () => {
    // Set up mock authentication
    cy.window().then((win) => {
      win.localStorage.setItem('authToken', 'mock-auth-token');
    });

    cy.visit('/');

    // Look for logout link or button
    cy.get('body').then(($body) => {
      const logoutSelectors = [
        'a:contains("Logout")',
        'a:contains("Sign out")',
        'button:contains("Logout")',
        'button:contains("Sign out")',
        '[data-testid*="logout"]',
        '.logout-button',
        '.sign-out',
      ];

      let foundLogout = false;
      logoutSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !foundLogout) {
          foundLogout = true;
          cy.get(selector).first().click();

          // Should redirect to logout page or home
          cy.url().should('satisfy', (url) => {
            return (
              url.includes('/logout') || url === Cypress.config().baseUrl + '/'
            );
          });
        }
      });

      if (!foundLogout) {
        // Try visiting logout URL directly
        cy.visit('/logout');
        cy.get('body').should('be.visible');
      }
    });

    // Verify auth token is cleared
    cy.window().then((win) => {
      expect(win.localStorage.getItem('authToken')).to.be.null;
    });
  });

  it('should redirect unauthenticated users from protected routes', () => {
    // Clear any existing auth
    cy.clearLocalStorage();

    // Try to visit profile page without authentication
    cy.visit('/profile', { failOnStatusCode: false });

    // Should redirect to login or show unauthorized message
    cy.url().then((url) => {
      if (url.includes('/login')) {
        cy.log('Redirected to login page - good');
        cy.get('body')
          .should('contain.text', 'Login')
          .or('contain.text', 'login');
      } else if (url.includes('/profile')) {
        // Check if page shows unauthorized message
        cy.get('body')
          .should('contain.text', 'unauthorized')
          .or('contain.text', 'login')
          .or('contain.text', 'sign in');
      }
    });
  });
});
