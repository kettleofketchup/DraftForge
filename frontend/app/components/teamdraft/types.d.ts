import { z } from 'zod';
import { TeamDraftRoundSchema, TeamDraftSchema } from './schemas';

// Primary types with explicit TeamDraft naming
export type TeamDraftType = z.infer<typeof TeamDraftSchema>;
export type TeamDraftRoundType = z.infer<typeof TeamDraftRoundSchema>;

export type TeamDraftStyleType = 'snake' | 'normal' | 'shuffle';

// Backwards compatibility aliases
export type DraftType = TeamDraftType;
export type DraftRoundType = TeamDraftRoundType;
export type DraftStyleType = TeamDraftStyleType;

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
