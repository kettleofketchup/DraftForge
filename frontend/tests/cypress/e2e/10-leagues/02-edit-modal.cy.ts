import {
  suppressHydrationErrors,
} from 'tests/cypress/support/utils';
import {
  getEditButton,
  getEditModal,
  getNameInput,
  getPrizeInput,
  getDescriptionInput,
  getRulesInput,
  getSubmitButton,
  visitLeaguePage,
  openEditModal,
  fillEditForm,
  submitEditForm,
} from 'tests/cypress/helpers/league';
import {
  TEST_LEAGUE_ID,
  EDITED_LEAGUE_NAME,
  TEST_PRIZE_POOL,
  TEST_DESCRIPTION,
} from './constants';

describe('League Page - Edit Modal (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    // Login as admin to have edit permissions
    cy.loginAdmin();
  });

  it('should show edit button for admin users', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Edit button should be visible
    getEditButton(cy).should('be.visible');
    getEditButton(cy).should('contain.text', 'Edit League');
  });

  it('should open edit modal when clicking edit button', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Click edit button
    openEditModal(cy);

    // Modal should be visible with correct elements
    cy.contains('Edit League').should('be.visible');
    getNameInput(cy).should('be.visible');
    getPrizeInput(cy).should('be.visible');
    getDescriptionInput(cy).should('be.visible');
    getRulesInput(cy).should('be.visible');
    getSubmitButton(cy).should('be.visible');
  });

  it('should close modal when clicking cancel', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Open modal
    openEditModal(cy);

    // Click cancel button
    cy.contains('button', 'Cancel').click();

    // Modal should be closed
    getEditModal(cy).should('not.exist');
  });

  it('should populate form with current league data', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Open modal
    openEditModal(cy);

    // Form should have current league data - name should not be empty
    getNameInput(cy).invoke('val').should('not.be.empty');
  });

  it('should validate required fields', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Open modal
    openEditModal(cy);

    // Clear name field (required)
    getNameInput(cy).clear();

    // Submit
    submitEditForm(cy);

    // Should show error message
    cy.contains(/required|name is required/i, { timeout: 5000 }).should(
      'be.visible',
    );
  });

  it('should update league successfully', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Open modal
    openEditModal(cy);

    // Fill form with new data
    fillEditForm(cy, {
      name: EDITED_LEAGUE_NAME,
      prizePool: TEST_PRIZE_POOL,
      description: TEST_DESCRIPTION,
    });

    // Submit
    submitEditForm(cy);

    // Should show success message
    cy.contains(/updated successfully|success/i, { timeout: 10000 }).should(
      'be.visible',
    );

    // Modal should close
    getEditModal(cy).should('not.exist');

    // Page should show updated name
    cy.contains(EDITED_LEAGUE_NAME, { timeout: 5000 }).should('be.visible');
  });

  it('should not show edit button for non-admin users', () => {
    // Login as regular user
    cy.loginUser();

    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Edit button should not be visible
    getEditButton(cy).should('not.exist');
  });
});

describe('League Page - Edit Modal Accessibility (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    cy.loginAdmin();
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');
    openEditModal(cy);
  });

  it('should have proper form labels', () => {
    // Check that form fields have associated labels
    cy.contains('label', 'League Name').should('be.visible');
    cy.contains('label', 'Prize Pool').should('be.visible');
    cy.contains('label', 'Description').should('be.visible');
    cy.contains('label', 'Rules').should('be.visible');
  });

  it('should close modal with Escape key', () => {
    // Press Escape key
    cy.get('body').type('{esc}');

    // Modal should be closed
    getEditModal(cy).should('not.exist');
  });
});
