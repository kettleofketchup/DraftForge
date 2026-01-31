import type {
  DraftRoundType,
  DraftType,
  GamesType,
  GameType,
  GuildMembers,
  TeamsType,
  TeamType,
  TournamentsType,
  TournamentType,
  UsersType,
  UserType,
} from '~/index';
import type { OrganizationType, OrganizationsType } from '~/components/organization/schemas';
import type { LeagueType, LeaguesType, LeagueMatchType } from '~/components/league/schemas';
import { getLogger } from '~/lib/logger';
import axios from './axios';
import type {
  CreateTeamFromCaptainAPI,
  DraftStyleMMRsAPIReturn,
  GetDraftStyleMMRsAPI,
  InitDraftRoundsAPI,
  PickPlayerForRoundAPI,
  RebuildDraftRoundsAPI,
  UndoPickAPI,
} from './types';
const log = getLogger('api');

export async function fetchCurrentUser(): Promise<UserType> {
  const response = await axios.get<UserType>(`/current_user`);
  return response.data;
}

export async function fetchUsers(): Promise<UsersType> {
  await refreshAvatars();
  const response = await axios.get<UsersType>(`/users`);
  return response.data;
}

export async function fetchUser(pk: number): Promise<UserType> {
  const response = await axios.get<UserType>(`/users/${pk}`);
  return response.data as UserType;
}

export async function deleteUser(userId: number): Promise<void> {
  await axios.delete(`/users/${userId}/`);
}

export async function createUser(data: Partial<UserType>): Promise<UserType> {
  const response = await axios.post(`/user/register`, data);
  return response.data as UserType;
}

export async function createTeam(data: Partial<TeamType>): Promise<TeamType> {
  const response = await axios.post(`/team/register`, data);
  return response.data as TeamType;
}

('use client');

export async function updateUser(
  userId: number,
  data: Partial<UserType>,
): Promise<UserType> {
  const response = await axios.patch<UserType>(`/users/${userId}/`, data);
  return response.data;
}
export async function get_dtx_members(): Promise<GuildMembers> {
  const response = await axios.get<GuildMembers>(`/discord/dtx_members`);
  if ('members' in response.data) {
    log.debug(response.data.members);
    return response.data.members as GuildMembers;
  } else {
    throw new Error("Key 'members' not found in response data");
  }
}
export async function getTournamentsBasic(): Promise<TournamentsType> {
  const response = await axios.get<TournamentsType>(`/tournaments-basic`);
  return response.data as TournamentsType;
}
export async function getTournaments(filters?: {
  organizationId?: number;
  leagueId?: number;
}): Promise<TournamentsType> {
  const params = new URLSearchParams();
  if (filters?.organizationId) {
    params.append('organization', filters.organizationId.toString());
  }
  if (filters?.leagueId) {
    params.append('league', filters.leagueId.toString());
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  // Use lightweight endpoint for list view (no nested teams/users)
  const response = await axios.get<TournamentsType>(`/tournaments-list/${queryString}`);
  return response.data as TournamentsType;
}

export async function getTeams(): Promise<TeamsType> {
  const response = await axios.get<TeamsType>(`/teams`);
  return response.data as TeamsType;
}

export async function getGames(): Promise<GamesType> {
  const response = await axios.get<GamesType>(`/games`);
  return response.data;
}

export async function createGame(data: Partial<GameType>): Promise<GameType> {
  const response = await axios.post(`/game/register`, data);
  return response.data as GameType;
}

export async function deleteTournament(pk: number): Promise<void> {
  await axios.delete(`/tournaments/${pk}/`);
}
export async function deleteGame(pk: number): Promise<void> {
  await axios.delete(`/games/${pk}/`);
}

export async function createTournament(
  data: Partial<TournamentType>,
): Promise<TournamentType> {
  const response = await axios.post(`/tournament/register`, data);
  return response.data as TournamentType;
}
export async function updateTournament(
  pk: number,
  data: Partial<TournamentType>,
): Promise<TournamentType> {
  const response = await axios.patch<TournamentType>(
    `/tournaments/${pk}/`,
    data,
  );
  return response.data;
}

export async function fetchTournament(pk: number): Promise<TournamentType> {
  log.debug(`Fetching tournament with pk: ${pk}`);
  const response = await axios.get<TournamentType>(`/tournaments/${pk}`);
  return response.data as TournamentType;
}
export async function fetchGame(pk: number): Promise<GameType> {
  const response = await axios.get<GameType>(`/games/${pk}`);
  return response.data as GameType;
}
export async function fetchTeam(pk: number): Promise<TeamType> {
  const response = await axios.get<TeamType>(`/teams/${pk}`);
  return response.data as TeamType;
}

export async function updateGame(
  pk: number,
  data: Partial<GameType>,
): Promise<GameType> {
  const response = await axios.patch<GameType>(`/games/${pk}`, data);
  return response.data;
}

export async function updateTeam(
  pk: number,
  data: Partial<TeamType>,
): Promise<TeamType> {
  const response = await axios.patch<TeamType>(`/teams/${pk}/`, data);
  return response.data;
}
export async function deleteTeam(pk: number): Promise<void> {
  await axios.delete(`/teams/${pk}/`);
}

export async function fetchDraft(pk: number): Promise<DraftType> {
  const response = await axios.get<DraftType>(`/drafts/${pk}/`);
  return response.data;
}

export async function updateDraft(
  pk: number,
  data: Partial<DraftType>,
): Promise<DraftType> {
  const response = await axios.patch<DraftType>(`/drafts/${pk}/`, data);
  return response.data;
}
export async function fetchDraftRound(pk: number): Promise<DraftRoundType> {
  const response = await axios.get<DraftRoundType>(`/draftrounds/${pk}/`);
  return response.data;
}

export async function updateDraftRound(
  pk: number,
  data: Partial<DraftRoundType>,
): Promise<DraftRoundType> {
  const response = await axios.patch<DraftRoundType>(
    `/draftrounds/${pk}/`,
    data,
  );
  return response.data;
}
export async function logout(): Promise<void> {
  await axios.post(`/logout`);
}
export async function refreshAvatars(): Promise<void> {
  axios.post(`/avatars/refresh/`);
}
export async function createDraft(
  pk: number,
  data: Partial<DraftType>,
): Promise<DraftType> {
  const response = await axios.post<DraftType>(`/drafts/${pk}/`, data);
  return response.data;
}

export async function deleteDraft(pk: number): Promise<void> {
  await axios.delete(`/drafts/${pk}/`);
}

export async function createDraftRound(
  pk: number,
  data: Partial<DraftRoundType>,
): Promise<DraftRoundType> {
  const response = await axios.post<DraftRoundType>(
    `/draftrounds/register`,
    data,
  );
  return response.data;
}

export async function deleteDraftRound(pk: number): Promise<void> {
  await axios.delete(`/draftrounds/${pk}/`);
}

export async function createTeamFromCaptain(
  data: CreateTeamFromCaptainAPI,
): Promise<TournamentType> {
  const response = await axios.post(
    `/tournaments/create-team-from-captain`,
    data,
  );
  return response.data as TournamentType;
}

export async function initDraftRounds(
  data: InitDraftRoundsAPI,
): Promise<TournamentType> {
  const response = await axios.post(`/tournaments/init-draft`, data);
  return response.data as TournamentType;
}

export async function DraftRebuild(
  data: RebuildDraftRoundsAPI,
): Promise<TournamentType> {
  const response = await axios.post(`/tournaments/draft-rebuild`, data);
  return response.data as TournamentType;
}

export async function PickPlayerForRound(
  data: PickPlayerForRoundAPI,
): Promise<TournamentType> {
  const response = await axios.post(`/tournaments/pick_player`, data);
  return response.data as TournamentType;
}

export async function UpdateProfile(
  data: Partial<UserType>,
): Promise<UserType> {
  const response = await axios.post(`/profile_update`, data);
  return response.data as UserType;
}

export async function getDraftStyleMMRs(
  data: GetDraftStyleMMRsAPI,
): Promise<DraftStyleMMRsAPIReturn> {
  const response = await axios.post(`/draft/get-style-mmrs`, data);
  return response.data as DraftStyleMMRsAPIReturn;
}

export async function undoLastPick(
  data: UndoPickAPI,
): Promise<TournamentType> {
  const response = await axios.post(`/tournaments/undo-pick`, data);
  return response.data as TournamentType;
}

// Organization API
export async function getOrganizations(): Promise<OrganizationsType> {
  const response = await axios.get<OrganizationsType>('/organizations/');
  return response.data;
}

export async function fetchOrganization(pk: number): Promise<OrganizationType> {
  const response = await axios.get<OrganizationType>(`/organizations/${pk}/`);
  return response.data;
}

export async function createOrganization(
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.post<OrganizationType>('/organizations/', data);
  return response.data;
}

export async function updateOrganization(
  pk: number,
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.patch<OrganizationType>(
    `/organizations/${pk}/`,
    data,
  );
  return response.data;
}

export async function deleteOrganization(pk: number): Promise<void> {
  await axios.delete(`/organizations/${pk}/`);
}

// League API
export async function getLeagues(organizationId?: number): Promise<LeaguesType> {
  const params = organizationId ? `?organization=${organizationId}` : '';
  const response = await axios.get<LeaguesType>(`/leagues/${params}`);
  return response.data;
}

// Home page stats - optimized endpoint returning only counts
export interface HomeStats {
  tournament_count: number;
  game_count: number;
  organization_count: number;
  league_count: number;
}

export async function getHomeStats(): Promise<HomeStats> {
  const response = await axios.get<HomeStats>('/home-stats/');
  return response.data;
}

export async function fetchLeague(pk: number): Promise<LeagueType> {
  const response = await axios.get<LeagueType>(`/leagues/${pk}/`);
  return response.data;
}

export async function createLeague(
  data: Partial<LeagueType>,
): Promise<LeagueType> {
  const response = await axios.post<LeagueType>('/leagues/', data);
  return response.data;
}

export async function updateLeague(
  pk: number,
  data: Partial<LeagueType>,
): Promise<LeagueType> {
  const response = await axios.patch<LeagueType>(`/leagues/${pk}/`, data);
  return response.data;
}

export async function deleteLeague(pk: number): Promise<void> {
  await axios.delete(`/leagues/${pk}/`);
}

export async function getLeagueMatches(
  leaguePk: number,
  options?: { tournament?: number; linkedOnly?: boolean }
): Promise<LeagueMatchType[]> {
  const params = new URLSearchParams();
  if (options?.tournament) params.append('tournament', options.tournament.toString());
  if (options?.linkedOnly) params.append('linked_only', 'true');

  const queryString = params.toString() ? `?${params.toString()}` : '';
  const response = await axios.get<LeagueMatchType[]>(
    `/leagues/${leaguePk}/matches/${queryString}`
  );
  return response.data;
}

// Admin Team API
export async function searchUsers(query: string): Promise<UserType[]> {
  const response = await axios.get<UserType[]>(`/users/search/?q=${encodeURIComponent(query)}`);
  return response.data;
}

interface AddUserResponse {
  status: string;
  user: UserType;
}

interface TransferOwnershipResponse {
  status: string;
  new_owner: UserType;
}

// Organization Admin Team
export async function addOrgAdmin(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/organizations/${orgId}/admins/`, { user_id: userId });
  return response.data.user;
}

export async function removeOrgAdmin(orgId: number, userId: number): Promise<void> {
  await axios.delete(`/organizations/${orgId}/admins/${userId}/`);
}

export async function addOrgStaff(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/organizations/${orgId}/staff/`, { user_id: userId });
  return response.data.user;
}

export async function removeOrgStaff(orgId: number, userId: number): Promise<void> {
  await axios.delete(`/organizations/${orgId}/staff/${userId}/`);
}

export async function transferOrgOwnership(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<TransferOwnershipResponse>(`/organizations/${orgId}/transfer-ownership/`, { user_id: userId });
  return response.data.new_owner;
}

// Organization Discord Members
export interface DiscordMember {
  user: {
    id: string;
    username: string;
    global_name?: string;
    avatar?: string;
  };
  nick?: string;
  joined_at: string;
}

export async function getOrganizationDiscordMembers(orgId: number): Promise<DiscordMember[]> {
  const response = await axios.get<{ members: DiscordMember[] }>(`/discord/organizations/${orgId}/discord-members/`);
  return response.data.members;
}

// League Admin Team
export async function addLeagueAdmin(leagueId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/leagues/${leagueId}/admins/`, { user_id: userId });
  return response.data.user;
}

export async function removeLeagueAdmin(leagueId: number, userId: number): Promise<void> {
  await axios.delete(`/leagues/${leagueId}/admins/${userId}/`);
}

export async function addLeagueStaff(leagueId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/leagues/${leagueId}/staff/`, { user_id: userId });
  return response.data.user;
}

export async function removeLeagueStaff(leagueId: number, userId: number): Promise<void> {
  await axios.delete(`/leagues/${leagueId}/staff/${userId}/`);
}
