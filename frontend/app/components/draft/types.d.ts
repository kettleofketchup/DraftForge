import { z } from 'zod';
import { DraftRoundSchema, DraftSchema } from './schemas';
export type DraftType = z.infer<typeof DraftSchema>;
export type DraftRoundType = z.infer<typeof DraftRoundSchema>;

export type DraftStyleType = 'snake' | 'normal' | 'shuffle';

export interface TieResolution {
  tied_teams: Array<{
    id: number;
    name: string;
    mmr: number;
  }>;
  roll_rounds: Array<
    Array<{
      team_id: number;
      roll: number;
    }>
  >;
  winner_id: number;
}

export interface PickResponse {
  success: boolean;
  pick: {
    round_id: number;
    player_id: number;
    team_id: number;
  };
  next_pick?: {
    captain_id: number;
    team_id: number;
    team_name: string;
    team_mmr: number;
  };
  tie_resolution?: TieResolution;
}
