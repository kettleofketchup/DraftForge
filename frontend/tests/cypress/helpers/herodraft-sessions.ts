/**
 * HeroDraft Session Helpers
 *
 * Provides fast captain identity switching using cy.session().
 * Uses Discord IDs for stable identification across populate runs.
 *
 * Captains are from Real Tournament 38's Winners Final game:
 * - Radiant: vrm.mtl vs Dire: ethan0688_
 */

import type { cyType } from './types';

// Discord IDs for Real Tournament 38 Winners Final captains
export const CAPTAIN_RADIANT = {
  discordId: '764290890617192469',
  username: 'vrm.mtl',
  sessionName: 'herodraft_captain_radiant',
} as const;

export const CAPTAIN_DIRE = {
  discordId: '1325607754177581066',
  username: 'ethan0688_',
  sessionName: 'herodraft_captain_dire',
} as const;

export type CaptainConfig = typeof CAPTAIN_RADIANT | typeof CAPTAIN_DIRE;

/**
 * Login as a captain using cy.session() for fast switching.
 * Sessions are cached - subsequent calls reuse existing session.
 */
export const loginAsCaptain = (cy: cyType, captain: CaptainConfig) => {
  cy.session(
    captain.sessionName,
    () => {
      cy.loginAsDiscordId(captain.discordId);
    },
    {
      validate: () => {
        // Validate session by checking current user endpoint
        cy.request({
          url: `${Cypress.env('apiUrl')}/api/current_user/`,
          failOnStatusCode: false,
        }).then((response: Cypress.Response<{ discordId: string }>) => {
          expect(response.status).to.eq(201);
          expect(response.body.discordId).to.eq(captain.discordId);
        });
      },
    },
  );
};

/**
 * Switch to Captain Radiant (vrm.mtl)
 */
export const switchToCaptainRadiant = (cy: cyType) => {
  loginAsCaptain(cy, CAPTAIN_RADIANT);
};

/**
 * Switch to Captain Dire (ethan0688_)
 */
export const switchToCaptainDire = (cy: cyType) => {
  loginAsCaptain(cy, CAPTAIN_DIRE);
};

/**
 * Get the other captain (for alternating turns)
 */
export const getOtherCaptain = (current: CaptainConfig): CaptainConfig => {
  return current === CAPTAIN_RADIANT ? CAPTAIN_DIRE : CAPTAIN_RADIANT;
};

/**
 * Clear all hero draft sessions (useful in beforeEach for clean state)
 */
export const clearHeroDraftSessions = (cy: cyType) => {
  Cypress.session.clearAllSavedSessions();
};
