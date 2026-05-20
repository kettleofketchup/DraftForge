/**
 * Playwright Test Fixtures
 *
 * Reference: docs/testing/auth/fixtures.md
 * If you update these fixtures, also update the documentation!
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
  loginUserClaimer,
  loginOrgAdmin,
  loginOrgStaff,
  loginOrgMember,
  loginLeagueAdmin,
  loginLeagueStaff,
  loginEventLeagueStaff,
  loginAuthMatrixOrgOwner,
  loginAuthMatrixOrgAdmin,
  loginAuthMatrixOrgStaff,
  loginAuthMatrixOrgMember,
  loginAuthMatrixLeagueAdmin,
  loginAuthMatrixLeagueStaff,
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

// Team Draft utilities
export {
  killDraftWebSocket,
  resetTeamDraft,
} from './teamdraft';

// Draft WebSocket helper
export { DraftWebSocketHelper } from '../helpers/DraftWebSocketHelper';

// Re-export the extended test from auth (primary test fixture)
export { test, expect } from './auth';

// Role-contexts matrix fixture — re-exported under a distinct name so
// spec files can opt in: ``import { roleMatrixTest } from '../../fixtures'``.
export {
  test as roleMatrixTest,
  setupRoleContexts,
  ROLE_NAMES,
  type RoleName,
  type RoleSession,
  type RoleContexts,
} from './role-contexts';

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
  resetTournamentByKey,
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

// AddUser modal helpers
export {
  waitForAddUserModal,
  closeAddUserModal,
  searchUser,
  searchAndAddUser,
  expectUserAlreadyAdded,
} from '../helpers/add-user';

// EditUser modal helpers
export {
  type EditUserField,
  type PositionKey,
  openEditModal,
  readEditField,
  fillEditField,
  saveEditModal,
  editUserField,
  restoreUserField,
  readPositionField,
  setPositionField,
} from '../helpers/edit-user';

// Events utilities
export {
  getEventsTestData,
  resetEventsData,
  triggerEventGeneration,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  setApprovedMmr,
  loginEventPlayerNoProfile,
  postWithCsrf,
  patchWithCsrf,
  syncDiscordEvents,
  simulateDiscordSignup,
  verifyDiscordMessages,
  sendTestNotification,
  EVENTS_ORG_NAME,
  EVENTS_EVENT_NAME,
  type EventInfo,
} from './events';
