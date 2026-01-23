/**
 * Playwright Test Fixtures
 *
 * Export all fixtures for easy importing in tests.
 * Uses named exports to avoid naming collisions.
 */

// Auth utilities (functions only, not the extended test)
export {
  loginAsUser,
  loginAsDiscordId,
  loginAdmin,
  loginStaff,
  loginUser,
  waitForHydration,
  visitAndWait,
  type UserInfo,
  type LoginResponse,
} from './auth';

// HeroDraft utilities
export {
  getHeroDraftByKey,
  resetHeroDraft,
  createTestHeroDraft,
  setupTwoCaptains,
  positionWindowsSideBySide,
  type HeroDraftInfo,
  type CaptainContext,
} from './herodraft';

// Re-export the extended test from auth (primary test fixture)
export { test, expect } from './auth';

// General utilities
export {
  visitAndWaitForHydration,
  waitForLoadingToComplete,
  navigateToRoute,
  checkBasicAccessibility,
  IGNORED_CONSOLE_PATTERNS,
  shouldIgnoreConsoleMessage,
} from '../helpers/utils';

// User card helpers
export {
  getUserCard,
  getUserRemoveButton,
  waitForUserCard,
  removeUser,
} from '../helpers/users';

// Tournament helpers
export {
  type TournamentData,
  TournamentPage,
  getTournamentByKey,
  navigateToTournament,
  clickTeamsTab,
  clickStartDraft,
  waitForDraftModal,
} from '../helpers/tournament';

// League helpers
export {
  type LeagueData,
  LeaguePage,
  navigateToLeague,
  clickLeagueTab,
  getLeagueEditModal,
  openLeagueEditModal,
  getFirstLeague,
} from '../helpers/league';
