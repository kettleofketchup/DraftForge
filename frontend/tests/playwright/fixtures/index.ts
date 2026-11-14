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
  loginAdmin,
  loginAsDiscordId,
  loginAsUser,
  loginAuthMatrixLeagueAdmin,
  loginAuthMatrixLeagueStaff,
  loginAuthMatrixOrgAdmin,
  loginAuthMatrixOrgMember,
  loginAuthMatrixOrgOwner,
  loginAuthMatrixOrgPromoter,
  loginAuthMatrixOrgStaff,
  loginEventLeagueStaff,
  loginLeagueAdmin,
  loginLeagueStaff,
  loginOrgAdmin,
  loginOrgMember,
  loginOrgStaff,
  loginStaff,
  loginUser,
  loginUserClaimer,
  visitAndWait,
  waitForHydration,
  type LoginResponse,
  type UserInfo,
} from './auth';

// HeroDraft utilities
export {
  createTestHeroDraft,
  getHeroDraftByKey,
  positionWindowsSideBySide,
  resetHeroDraft,
  setupTwoCaptains,
  type CaptainContext,
  type HeroDraftInfo,
} from './herodraft';

// Team Draft utilities
export {
  activeRound,
  captainsOf,
  draftStateOf,
  expireDraftClock,
  fetchTimerTournament,
  killDraftWebSocket,
  openCaptainPage,
  openDraftModal,
  readyUp,
  resetTeamDraft,
  resetTimerTournament,
  resumeDraftAsStaff,
  staffPick,
  staleDraftHeartbeat,
  startDraftAsStaff,
  suppressDraftHeartbeats,
  type TimerTournament,
} from './teamdraft';

// Draft WebSocket helper
export { DraftWebSocketHelper } from '../helpers/DraftWebSocketHelper';

// Re-export the extended test from auth (primary test fixture)
export { expect, test } from './auth';

// Role-contexts matrix fixture — re-exported under a distinct name so
// spec files can opt in: ``import { roleMatrixTest } from '../../fixtures'``.
export {
  ROLE_NAMES,
  test as roleMatrixTest,
  setupRoleContexts,
  type RoleContexts,
  type RoleName,
  type RoleSession,
} from './role-contexts';

// General utilities
export {
  IGNORED_CONSOLE_PATTERNS,
  checkBasicAccessibility,
  navigateToRoute,
  shouldIgnoreConsoleMessage,
  visitAndWaitForHydration,
  waitForLoadingToComplete,
} from '../helpers/utils';

// User card helpers
export {
  getUserCard,
  getUserRemoveButton,
  removeUser,
  waitForUserCard,
} from '../helpers/users';

// Tournament helpers
export {
  TournamentPage,
  clickStartDraft,
  clickTeamsTab,
  getTournamentByKey,
  navigateToTournament,
  resetTournamentByKey,
  waitForDraftModal,
  type TournamentData,
} from '../helpers/tournament';

// League helpers
export {
  LeaguePage,
  clickLeagueTab,
  getFirstLeague,
  getLeagueEditModal,
  navigateToLeague,
  openLeagueEditModal,
  type LeagueData,
} from '../helpers/league';

// AddUser modal helpers
export {
  closeAddUserModal,
  expectUserAlreadyAdded,
  searchAndAddUser,
  searchUser,
  waitForAddUserModal,
} from '../helpers/add-user';

// EditUser modal helpers
export {
  editUserField,
  fillEditField,
  openEditModal,
  readEditField,
  readPositionField,
  restoreUserField,
  saveEditModal,
  setPositionField,
  type EditUserField,
  type PositionKey,
} from '../helpers/edit-user';

// Events utilities
export {
  EVENTS_EVENT_NAME,
  EVENTS_ORG_NAME,
  getEventsTestData,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  loginEventPlayerNoProfile,
  patchWithCsrf,
  postWithCsrf,
  resetEventsData,
  sendTestNotification,
  setApprovedMmr,
  simulateDiscordSignup,
  syncDiscordEvents,
  triggerEventGeneration,
  verifyDiscordMessages,
  type EventInfo,
} from './events';

// dota_lobby utilities (18-dota-lobby specs, simulated dota_lobby)
export {
  SIMULATOR_SKIP_REASON,
  bracketNode,
  closeMatchModal,
  expectLobbyState,
  getDotaLobbyTestData,
  getLobbyRow,
  getSimLobby,
  hasSimulator,
  loginDotaLobby,
  openBracket,
  openMatchModal,
  requestLobby,
  resetDotaLobbyData,
  seedLobbyRow,
  sim,
  simulatorStatus,
  waitForLobbyRow,
  type DotaLobbyRole,
  type DotaLobbyTestData,
  type LobbyGame,
  type LobbyPlayer,
  type LobbyRow,
  type LobbyTournament,
  type SimLobby,
  type SimulatorStatus,
} from './dota-lobby';

// Org paid features utilities (19-org-features specs)
export {
  expectNoSessionToast,
  getOrgFeaturesData,
  leaderboardByUser,
  loginOrgFeatures,
  moveEventToRollCall,
  orgFeaturesApi,
  resetOrgFeatures,
  type LeaderboardRowRef,
  type OrgFeaturesEvent,
  type OrgFeaturesRef,
  type OrgFeaturesRole,
  type OrgFeaturesTestData,
} from './org-features';
