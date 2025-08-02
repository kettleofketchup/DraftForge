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
import { getLogger } from '~/lib/logger';
import axios from './axios';
import type { CreateTeamFromCaptainAPI } from './types';
const log = getLogger('api');

export async function fetchCurrentUser(): Promise<UserType> {
  const response = await axios.get<UserType>(`/current_user`);
  return response.data;
}

export async function fetchUsers(): Promise<UsersType> {
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
  const response = await axios.get<GuildMembers>(`/dtx_members`);
  if ('members' in response.data) {
    log.debug(response.data.members);
    return response.data.members as GuildMembers;
  } else {
    throw new Error("Key 'members' not found in response data");
  }
}

export async function getTournaments(): Promise<TournamentsType> {
  const response = await axios.get<TournamentsType>(`/tournaments`);
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

export async function deleteTournament(pk: number): Promise<void> {
  await axios.delete(`/tournament/${pk}/`);
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
export async function fetchDraftRound(pk: number): Promise<DraftRoundType> {
  const response = await axios.get<DraftRoundType>(`/draftrounds/${pk}/`);
  return response.data;
}

export async function logout(): Promise<void> {
  await axios.post(`/logout`);
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
