/**
 * API Barrel File
 *
 * Re-exports all domain-specific API functions.
 * All consumers import from this file.
 */

// Tournament
export {
  getTournamentsBasic,
  getTournaments,
  fetchTournament,
  createTournament,
  updateTournament,
  deleteTournament,
  addTournamentMember,
} from './tournamentAPI';

// Draft
export {
  fetchDraft,
  updateDraft,
  createDraft,
  deleteDraft,
  fetchDraftRound,
  updateDraftRound,
  createDraftRound,
  deleteDraftRound,
  createTeamFromCaptain,
  initDraftRounds,
  DraftRebuild,
  PickPlayerForRound,
  undoLastPick,
  getDraftStyleMMRs,
} from './draftAPI';

// User
export {
  fetchCurrentUser,
  logout,
  fetchUsers,
  fetchUser,
  createUser,
  updateUser,
  deleteUser,
  UpdateProfile,
  claimUserProfile,
  refreshAvatars,
  searchUsers,
  get_dtx_members,
  type SearchUserResult,
} from './userAPI';

// Team
export {
  createTeam,
  getTeams,
  fetchTeam,
  updateTeam,
  deleteTeam,
} from './teamAPI';

// Game
export {
  createGame,
  getGames,
  fetchGame,
  updateGame,
  deleteGame,
} from './gameAPI';

// Home
export { getHomeStats, type HomeStats } from './homeAPI';

// Organization
export {
  getOrganizations,
  fetchOrganization,
  createOrganization,
  updateOrganization,
  deleteOrganization,
  addOrgAdmin,
  removeOrgAdmin,
  addOrgStaff,
  removeOrgStaff,
  transferOrgOwnership,
  getOrganizationUsers,
  updateOrgUser,
  getOrganizationDiscordMembers,
  type DiscordMember,
  getClaimRequests,
  approveClaimRequest,
  rejectClaimRequest,
  type ProfileClaimRequest,
  addOrgMember,
  searchDiscordMembers,
  refreshDiscordMembers,
  type DiscordSearchResult,
  importCSVToOrg,
  importCSVToTournament,
  type CSVImportRow,
  type CSVImportOptions,
  type CSVImportResponse,
  type CSVImportResultRow,
  type MMRTarget,
} from './orgAPI';

// League
export {
  getLeagues,
  fetchLeague,
  createLeague,
  updateLeague,
  deleteLeague,
  getLeagueMatches,
  addLeagueAdmin,
  removeLeagueAdmin,
  addLeagueStaff,
  removeLeagueStaff,
  getLeagueUsers,
  addLeagueMember,
} from './leagueAPI';

// Shared types
export type { AddMemberPayload, AddUserResponse } from './types';
