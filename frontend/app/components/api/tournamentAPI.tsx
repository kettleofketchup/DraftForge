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
import type { DraftOptionsPatch } from '~/components/teamdraft/schemas';
import type { DiscordTournamentLogEntry } from '~/components/tournament/schemas';
import type { PaginatedTournaments, TournamentBucket } from '~/components/tournament/types';
import type { AddMemberPayload, AddUserResponse } from './types';
import { isAxiosError } from 'axios';
import { getLogger } from '~/lib/logger';
import axios from './axios';

const log = getLogger('api');

export async function getTournamentsBasic(): Promise<TournamentsType> {
  const response = await axios.get<TournamentsType>(`/tournaments-basic/`);
  return response.data as TournamentsType;
}

export interface TournamentListFilters {
  organizationId?: number;
  /** Any of these organizations; an empty list matches none. */
  organizationIds?: number[];
  /** Also include tournaments whose source event takes user signups. */
  openSignups?: boolean;
  leagueId?: number;
  bucket?: TournamentBucket;
  search?: string;
}

function tournamentListParams(filters?: TournamentListFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters?.bucket !== undefined) params.append('bucket', filters.bucket);
  if (Number.isFinite(filters?.organizationId)) {
    params.append('organization', String(filters?.organizationId));
  }
  if (filters?.organizationIds !== undefined) {
    params.append('organizations', filters.organizationIds.join(','));
  }
  if (filters?.openSignups) params.append('open_signups', '1');
  if (Number.isFinite(filters?.leagueId)) {
    params.append('league', String(filters?.leagueId));
  }
  if (filters?.search !== undefined) params.append('search', filters.search);
  return params;
}

export async function getTournaments(filters?: TournamentListFilters): Promise<TournamentsType> {
  const params = tournamentListParams(filters).toString();
  const queryString = params ? `?${params}` : '';
  const response = await axios.get<TournamentsType>(`/tournaments-list/${queryString}`);
  return response.data;
}

// An archive that shrank between loads 404s past its new last page: end of list.
export async function getTournamentsPage(
  filters: TournamentListFilters & { page: number; pageSize?: number },
): Promise<PaginatedTournaments> {
  const params = tournamentListParams(filters);
  params.append('page', String(filters.page));
  if (filters.pageSize !== undefined) params.append('page_size', String(filters.pageSize));
  try {
    const response = await axios.get<PaginatedTournaments>(`/tournaments-list/?${params.toString()}`);
    return response.data;
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 404 && filters.page > 1) {
      return { count: 0, next: null, previous: null, results: [] };
    }
    throw e;
  }
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

export async function updateDraftOptions(
  tournamentPk: number,
  patch: DraftOptionsPatch,
): Promise<TournamentType> {
  const response = await axios.patch<TournamentType>(
    `/tournaments/${tournamentPk}/`,
    { draft_options: patch },
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

export type { DiscordTournamentLogEntry } from '~/components/tournament/schemas';

export async function fetchDiscordTournamentLogs(
  tournamentId: number,
): Promise<DiscordTournamentLogEntry[]> {
  const response = await axios.get<DiscordTournamentLogEntry[]>(
    `/tournaments/${tournamentId}/discord-logs/`,
  );
  return response.data;
}
