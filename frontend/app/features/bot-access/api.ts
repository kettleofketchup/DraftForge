import { AxiosHeaders, isAxiosError } from 'axios';
import api from '~/components/api/axios';
import { BotAccessSnapshotSchema, type BotAccessSnapshot } from './schemas';

export async function getBotAccess(
  leagueId: number,
): Promise<BotAccessSnapshot> {
  const response = await api.get(`/leagues/${leagueId}/bot-access/`);
  return BotAccessSnapshotSchema.parse(response.data);
}

export async function refreshBotAccess(
  leagueId: number,
): Promise<BotAccessSnapshot> {
  const response = await api.post(`/leagues/${leagueId}/bot-access/refresh/`);
  return BotAccessSnapshotSchema.parse(response.data);
}

export function httpStatus(err: unknown): number | null {
  return isAxiosError(err) ? (err.response?.status ?? null) : null;
}

export function retryAfterSeconds(err: unknown): number | null {
  if (!isAxiosError(err) || err.response?.status !== 429) return null;
  const headers: unknown = err.response.headers;
  const raw: unknown =
    headers instanceof AxiosHeaders
      ? headers.get('retry-after')
      : (headers as Record<string, unknown> | undefined)?.['retry-after'];
  if (typeof raw !== 'string' || !/^\d+$/.test(raw.trim())) return null;
  return Math.max(1, Number(raw.trim()));
}
