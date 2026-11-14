import { z } from 'zod';
import api from '~/components/api/axios';
import {
  ALL_TIME,
  AdminEntrySchema,
  ENTRIES_PAGE_SIZE,
  EntriesPageSchema,
  LeaderboardResponseSchema,
  MemberBreakdownSchema,
  PointValueRowSchema,
  PointValueUpdateResultSchema,
  type AdminEntry,
  type EntriesFilters,
  type EntriesPage,
  type LeaderboardResponse,
  type ManualAwardInput,
  type MemberBreakdown,
  type PointValueRow,
  type PointValueUpdate,
  type PointValueUpdateResult,
  type RatedKind,
} from './schemas';

function periodParams(period: string): { period?: string } {
  return period && period !== ALL_TIME ? { period } : {};
}

export async function getLeaderboard(orgId: number, period: string): Promise<LeaderboardResponse> {
  const response = await api.get(`/organizations/${orgId}/contributions/leaderboard/`, {
    params: periodParams(period),
  });
  return LeaderboardResponseSchema.parse(response.data);
}

export async function getMemberBreakdown(
  orgId: number,
  orgUserPk: number,
  period: string,
): Promise<MemberBreakdown> {
  const response = await api.get(`/organizations/${orgId}/contributions/members/${orgUserPk}/`, {
    params: periodParams(period),
  });
  return MemberBreakdownSchema.parse(response.data);
}

export async function getPointValues(orgId: number): Promise<PointValueRow[]> {
  const response = await api.get(`/organizations/${orgId}/contributions/point-values/`);
  return z.array(PointValueRowSchema).parse(response.data);
}

export async function setPointValue(
  orgId: number,
  kind: RatedKind,
  update: PointValueUpdate,
): Promise<PointValueUpdateResult> {
  const response = await api.put(
    `/organizations/${orgId}/contributions/point-values/${kind}/`,
    update,
  );
  return PointValueUpdateResultSchema.parse(response.data);
}

export async function getEntries(orgId: number, filters: EntriesFilters): Promise<EntriesPage> {
  const response = await api.get(`/organizations/${orgId}/contributions/entries/`, {
    params: {
      ...periodParams(filters.period),
      ...(filters.kind ? { kind: filters.kind } : {}),
      limit: ENTRIES_PAGE_SIZE,
      offset: filters.offset,
    },
  });
  return EntriesPageSchema.parse(response.data);
}

export async function createManualAward(
  orgId: number,
  input: ManualAwardInput,
): Promise<AdminEntry> {
  const response = await api.post(`/organizations/${orgId}/contributions/entries/`, input);
  return AdminEntrySchema.parse(response.data);
}

export type ManualAwardUpdate = Partial<Omit<ManualAwardInput, 'user_id'>>;

export async function updateManualAward(
  orgId: number,
  entryPk: number,
  changes: ManualAwardUpdate,
): Promise<AdminEntry> {
  const response = await api.patch(
    `/organizations/${orgId}/contributions/entries/${entryPk}/`,
    changes,
  );
  return AdminEntrySchema.parse(response.data);
}

export async function deleteManualAward(orgId: number, entryPk: number): Promise<void> {
  await api.delete(`/organizations/${orgId}/contributions/entries/${entryPk}/`);
}
