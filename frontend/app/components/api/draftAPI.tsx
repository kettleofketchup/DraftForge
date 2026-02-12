/**
 * Draft API
 *
 * API functions for draft and draft round operations.
 */

import type {
  DraftRoundType,
  DraftType,
  TournamentType,
} from '~/index';
import type {
  CreateTeamFromCaptainAPI,
  DraftStyleMMRsAPIReturn,
  GetDraftStyleMMRsAPI,
  InitDraftRoundsAPI,
  PickPlayerForRoundAPI,
  RebuildDraftRoundsAPI,
  UndoPickAPI,
} from './types';
import axios from './axios';

// Draft CRUD
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

// DraftRound CRUD
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

// Draft actions (tournament-scoped)
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

export async function undoLastPick(
  data: UndoPickAPI,
): Promise<TournamentType> {
  const response = await axios.post(`/tournaments/undo-pick`, data);
  return response.data as TournamentType;
}

export async function getDraftStyleMMRs(
  data: GetDraftStyleMMRsAPI,
): Promise<DraftStyleMMRsAPIReturn> {
  const response = await axios.post(`/draft/get-style-mmrs`, data);
  return response.data as DraftStyleMMRsAPIReturn;
}
