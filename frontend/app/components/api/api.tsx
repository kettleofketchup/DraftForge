/**
 * API Barrel File
 *
 * Re-exports all domain-specific API functions.
 * All consumers import from this file.
 */

// Tournament
export {
  addTournamentMember,
  createTournament,
  deleteTournament,
  fetchDiscordTournamentLogs,
  fetchTournament,
  getTournaments,
  getTournamentsBasic,
  getTournamentsPage,
  removeTournamentMember,
  updateTournament,
} from './tournamentAPI';

export type {
  DiscordTournamentLogEntry,
  TournamentListFilters,
} from './tournamentAPI';

// Draft
export {
  DraftRebuild,
  PickPlayerForRound,
  createDraft,
  createDraftRound,
  createTeamFromCaptain,
  deleteDraft,
  deleteDraftRound,
  fetchDraft,
  fetchDraftRound,
  getDraftStyleMMRs,
  initDraftRounds,
  undoLastPick,
  updateDraft,
  updateDraftRound,
} from './draftAPI';

// User
export {
  UpdateProfile,
  claimUserProfile,
  createUser,
  deleteUser,
  fetchCurrentUser,
  fetchUser,
  fetchUsers,
  fetchUsersBulk,
  get_dtx_members,
  logout,
  profileFriendIdError,
  refreshAvatars,
  searchUsers,
  updateUser,
  type SearchUserResult,
} from './userAPI';

// Team
export {
  createTeam,
  deleteTeam,
  fetchTeam,
  fetchTeamUsage,
  getTeams,
  updateTeam,
} from './teamAPI';

// Game
export {
  createGame,
  deleteGame,
  fetchGame,
  getGames,
  updateGame,
} from './gameAPI';

// Home
export { getHomeStats, type HomeStats } from './homeAPI';

// Organization
export {
  addOrgAdmin,
  addOrgMember,
  addOrgPromoter,
  addOrgStaff,
  createOrganization,
  deleteOrganization,
  fetchOrganization,
  getOrgPromoters,
  getOrganizationDiscordMembers,
  getOrganizationUsers,
  getOrganizations,
  importCSVToOrg,
  importCSVToTournament,
  refreshDiscordMembers,
  rejectClaimRequest,
  removeOrgAdmin,
  removeOrgPromoter,
  removeOrgStaff,
  searchDiscordMembers,
  transferOrgOwnership,
  updateOrgUser,
  updateOrganization,
  type CSVImportOptions,
  type CSVImportResponse,
  type CSVImportResultRow,
  type CSVImportRow,
  type DiscordMember,
  type DiscordSearchResult,
  type MMRTarget,
  type ProfileClaimRequest,
} from './orgAPI';

// League
export {
  addLeagueAdmin,
  addLeagueMember,
  addLeagueStaff,
  createLeague,
  deleteLeague,
  fetchLeague,
  getLeagueMatches,
  getLeagueUsers,
  getLeagues,
  removeLeagueAdmin,
  removeLeagueStaff,
  updateLeague,
} from './leagueAPI';

// Shared types
export type { AddMemberPayload, AddUserResponse } from './types';

// Events
export {
  adminAddSignup,
  approveSignup,
  cancelEvent,
  cancelSignup,
  completeEvent,
  confirmSignup,
  createEvent,
  createEventRepeater,
  createSeriesOneOffEvent,
  deleteEvent,
  deleteEventRepeater,
  demoteSignup,
  getDiscordChannels,
  getDiscordRoles,
  getEvent,
  getEventDiscordState,
  getEventRepeater,
  getEventRepeaters,
  getEventSignupHistory,
  getEventSignups,
  getEvents,
  getOrgEventDefaults,
  getRepeaterSubscribers,
  openSignups,
  reactivateRepeater,
  reinstateSignup,
  rejectSignup,
  reopenSignups,
  restartTournament,
  setEventStaff,
  signupForEvent,
  startRollCall,
  startTournament,
  subscribeToRepeater,
  unconfirmSignup,
  unsubscribeFromRepeater,
  updateEvent,
  updateEventRepeater,
  updateOrgEventDefaults,
} from './eventsAPI';

export type {
  EventSignupType,
  EventTeamType,
  EventType,
} from '~/components/events/schemas';
export type {
  DiscordChannel,
  DiscordRole,
  EventRepeaterListItem,
  EventRepeaterType,
  EventStaffPayload,
  EventWritePayload,
  OrgEventDefaultsType,
  RepeaterSubscriber,
  SignupBody,
} from './eventsAPI';

// Org settings
export {
  OrgSettingsSchema,
  StaffOverridePolicySchema,
  StaffPlacementFormSchema,
  getOrgSettings,
  orgSettingsKey,
  patchOrgSettings,
} from './orgSettingsAPI';
export type {
  OrgSettings,
  StaffOverridePolicy,
  StaffPlacementFormValues,
} from './orgSettingsAPI';
