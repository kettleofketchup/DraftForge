/**
 * League API
 *
 * API functions for league-related operations.
 */

import type { LeagueType, LeaguesType, LeagueMatchType } from '~/components/league/schemas';
import type { UserType } from '~/index';
import axios from './axios';

// Response types
interface AddUserResponse {
  status: string;
  user: UserType;
}

// League CRUD
export async function getLeagues(organizationId?: number): Promise<LeaguesType> {
  const params = organizationId ? `?organization=${organizationId}` : '';
  const response = await axios.get<LeaguesType>(`/leagues/${params}`);
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

// League Matches
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

// League Users (members via LeagueUser)
export async function getLeagueUsers(leagueId: number): Promise<UserType[]> {
  const response = await axios.get<UserType[]>(`/leagues/${leagueId}/users/`);
  return response.data;
}
