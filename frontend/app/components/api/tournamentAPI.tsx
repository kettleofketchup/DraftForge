/**
 * Tournament API
 *
 * API functions for tournament-related operations.
 */

import type {
  TournamentsType,
  TournamentType,
  UserType,
} from '~/index';
import type { AddMemberPayload, AddUserResponse } from './types';
import { getLogger } from '~/lib/logger';
import axios from './axios';

const log = getLogger('api');

export async function getTournamentsBasic(): Promise<TournamentsType> {
  const response = await axios.get<TournamentsType>(`/tournaments-basic/`);
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

export async function fetchTournament(pk: number): Promise<TournamentType> {
  log.debug(`Fetching tournament with pk: ${pk}`);
  const response = await axios.get<TournamentType>(`/tournaments/${pk}/`);
  return response.data as TournamentType;
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

export async function deleteTournament(pk: number): Promise<void> {
  await axios.delete(`/tournaments/${pk}/`);
}

export async function addTournamentMember(
  tournamentId: number,
  payload: AddMemberPayload,
): Promise<TournamentType> {
  const response = await axios.post<{ status: string; tournament: TournamentType }>(
    `/tournaments/${tournamentId}/members/`,
    payload,
  );
  return response.data.tournament;
}
