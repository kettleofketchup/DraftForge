import api from '~/components/api/axios';
import type { MmrScope } from './queryKeys';
import {
  MmrChangeRequestSchema,
  MmrRequestListSchema,
  PendingCountSchema,
  UserMmrSummarySchema,
  type CreateMmrRequestInput,
  type MmrChangeRequest,
  type MmrQueueStatus,
  type PendingCount,
  type StaffSetMmrInput,
  type UserMmrSummary,
} from './schemas';

function scopeBase(scope: MmrScope): string {
  return 'org' in scope
    ? `/organizations/${scope.org}/mmr-requests`
    : `/leagues/${scope.league}/mmr-requests`;
}

function targetForm(input: CreateMmrRequestInput | StaffSetMmrInput): FormData {
  const form = new FormData();
  form.append('target', input.target);
  if (input.target === 'org') {
    form.append('org_user', String(input.orgUserPk));
    form.append('game_type', String(input.gameType));
  } else {
    form.append('league_user', String(input.leagueUserPk));
  }
  if (input.note) form.append('note', input.note);
  return form;
}

export function mmrScreenshotUrl(id: number): string {
  return `/api/mmr-requests/${id}/screenshot/`;
}

export async function fetchUserMmrSummary(
  userPk: number,
): Promise<UserMmrSummary> {
  const response = await api.get(`/users/${userPk}/mmrs/`);
  return UserMmrSummarySchema.parse(response.data);
}

export async function fetchMyMmrRequests(): Promise<MmrChangeRequest[]> {
  const response = await api.get('/mmr-requests/mine/');
  return MmrRequestListSchema.parse(response.data);
}

export async function createMmrRequest(
  input: CreateMmrRequestInput,
): Promise<MmrChangeRequest> {
  const form = targetForm(input);
  form.append('requested_mmr', String(input.requestedMmr));
  form.append('screenshot', input.screenshot);
  const response = await api.post('/mmr-requests/', form);
  return MmrChangeRequestSchema.parse(response.data);
}

export async function cancelMmrRequest(id: number): Promise<MmrChangeRequest> {
  const response = await api.post(`/mmr-requests/${id}/cancel/`);
  return MmrChangeRequestSchema.parse(response.data);
}

export async function fetchMmrQueue(
  scope: MmrScope,
  status: MmrQueueStatus,
): Promise<MmrChangeRequest[]> {
  const response = await api.get(`${scopeBase(scope)}/`, {
    params: { status },
  });
  return MmrRequestListSchema.parse(response.data);
}

export async function fetchMmrPendingCount(
  scope: MmrScope,
): Promise<PendingCount> {
  const response = await api.get(`${scopeBase(scope)}/pending-count/`);
  return PendingCountSchema.parse(response.data);
}

export async function approveMmrRequest(
  id: number,
  mmr?: number,
): Promise<MmrChangeRequest> {
  const response = await api.post(
    `/mmr-requests/${id}/approve/`,
    mmr == null ? {} : { mmr },
  );
  return MmrChangeRequestSchema.parse(response.data);
}

export async function rejectMmrRequest(
  id: number,
  reason: string,
): Promise<MmrChangeRequest> {
  const response = await api.post(`/mmr-requests/${id}/reject/`, { reason });
  return MmrChangeRequestSchema.parse(response.data);
}

export async function staffSetMmr(
  scope: MmrScope,
  input: StaffSetMmrInput,
): Promise<MmrChangeRequest> {
  const form = targetForm(input);
  form.append('mmr', String(input.mmr));
  if (input.screenshot) form.append('screenshot', input.screenshot);
  const response = await api.post(`${scopeBase(scope)}/staff-set/`, form);
  return MmrChangeRequestSchema.parse(response.data);
}
