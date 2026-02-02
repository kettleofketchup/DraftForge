import { api } from './axios';
import { BracketResponseSchema } from '~/components/bracket/schemas';
import type { BracketMatch, BracketResponse } from '~/components/bracket/types';

/**
 * Save bracket matches to backend
 */
export async function saveBracket(
  tournamentId: number,
  matches: BracketMatch[]
): Promise<BracketResponse> {
  const response = await api.post(`/bracket/tournaments/${tournamentId}/save/`, {
    matches,
  });
  return BracketResponseSchema.parse(response.data);
}

/**
 * Load bracket from backend
 */
export async function loadBracket(tournamentId: number): Promise<BracketResponse> {
  const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
  return BracketResponseSchema.parse(response.data);
}
