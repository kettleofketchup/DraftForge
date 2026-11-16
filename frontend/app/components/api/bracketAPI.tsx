import type {
  BracketMatchDTO,
  BracketResponseDTO,
} from '~/components/bracket/schemas';
import {
  BracketMatchSchema,
  BracketResponseSchema,
} from '~/components/bracket/schemas';
import type { BracketMatch } from '~/components/bracket/types';
import { api } from './axios';

/**
 * Persist one game's result; the backend advances the winner and loser into
 * their next games. `null` unsets the result and pulls them back out.
 */
export async function advanceWinner(
  gameId: number,
  winner: 'radiant' | 'dire' | null,
): Promise<BracketMatchDTO> {
  const response = await api.post(`/bracket/games/${gameId}/advance-winner/`, {
    winner,
  });
  return BracketMatchSchema.parse(response.data);
}

/**
 * Save bracket matches to backend
 */
export async function saveBracket(
  tournamentId: number,
  matches: BracketMatch[],
): Promise<BracketResponseDTO> {
  const response = await api.post(
    `/bracket/tournaments/${tournamentId}/save/`,
    {
      matches,
    },
  );
  return BracketResponseSchema.parse(response.data);
}

/**
 * Load bracket from backend
 */
export async function loadBracket(
  tournamentId: number,
): Promise<BracketResponseDTO> {
  const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
  return BracketResponseSchema.parse(response.data);
}
