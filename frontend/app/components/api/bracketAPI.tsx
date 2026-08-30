import { api } from './axios';
import { BracketResponseSchema } from '~/components/bracket/schemas';
import type { BracketMatch } from '~/components/bracket/types';
import type { BracketResponseDTO } from '~/components/bracket/schemas';

/**
 * Save bracket matches to backend
 */
export async function saveBracket(
  tournamentId: number,
  matches: BracketMatch[]
): Promise<BracketResponseDTO> {
  const response = await api.post(`/bracket/tournaments/${tournamentId}/save/`, {
    matches,
  });
  return BracketResponseSchema.parse(response.data);
}

/**
 * Load bracket from backend
 */
export async function loadBracket(tournamentId: number): Promise<BracketResponseDTO> {
  const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
  return BracketResponseSchema.parse(response.data);
}
