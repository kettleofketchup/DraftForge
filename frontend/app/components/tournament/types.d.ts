import { z } from 'zod';
import { DraftSchema } from '../draft/types';
import { GameSchema } from '../game/types';
import { UserSchema } from '../user/user';
import { STATE_CHOICES, TOURNAMENT_TYPE } from './constants';
import { TeamSchema, TournamentSchema } from './schemas';

// Re-export types from other modules for convenience
export type { GameType } from '../game/types';

// Re-export constants
export { STATE_CHOICES, TOURNAMENT_TYPE };

export type TeamType = z.infer<typeof TeamSchema>;
export type TournamentType = z.infer<typeof TournamentSchema>;

export declare interface TournamentClassType extends TournamentType {
  dbFetch: () => Promise<void>;
  dbUpdate: (data: Partial<TournamentType>) => Promise<void>;
  dbCreate: () => Promise<void>;
  dbDelete: () => Promise<void>;
}

export type TournamentsType = TournamentType[];
export type TeamsType = TeamType[];
