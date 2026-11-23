import { z } from 'zod';
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

// set_team_placement in backend/app/views/bracket.py
export const SetTeamPlacementResponseSchema = z.object({
  team_id: z.number(),
  placement: z.number().nullable(),
});
export type SetTeamPlacementResponse = z.infer<
  typeof SetTeamPlacementResponseSchema
>;

/**
 * Set or clear (`null`) a team's placement. Clearing returns 409
 * `roster_conflict` when it would put a player on two live teams.
 */
export async function setTeamPlacement(
  tournamentId: number,
  teamId: number,
  placement: number | null,
): Promise<SetTeamPlacementResponse> {
  const response = await api.patch(
    `/bracket/tournaments/${tournamentId}/teams/${teamId}/placement/`,
    { placement },
  );
  return SetTeamPlacementResponseSchema.parse(response.data);
}

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
