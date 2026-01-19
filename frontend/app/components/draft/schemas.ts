import { z } from 'zod';
import { TeamSchema } from '../team/schemas';
import { UserSchema } from '../user/schemas';

export const DraftRoundSchema = z.object({
  pk: z.number().nullable(),
  draft: z.any(), // To be replaced with DraftSchema
  captain: UserSchema.nullable(),
  pick_number: z.number().min(1).nullable(),
  pick_phase: z.number().min(1).nullable(),
  choice: UserSchema.nullable(),
  team: TeamSchema.nullable(),
});

// Use z.lazy() to avoid circular dependency with TournamentSchema
export const DraftSchema = z.object({
  pk: z.number().nullable(),
  tournament: z.lazy(() => z.any()).nullable(), // Lazy reference to avoid circular import
  users_remaining: z.array(UserSchema).nullable(),
  draft_rounds: z.array(DraftRoundSchema).nullable(),
  latest_round: z.number().nullable(),
  draft_style: z.enum(['snake', 'normal', 'shuffle']).default('snake'),
  snake_first_pick_mmr: z.number().default(0),
  snake_last_pick_mmr: z.number().default(0),
  normal_first_pick_mmr: z.number().default(0),
  normal_last_pick_mmr: z.number().default(0),
  current_draft_first_pick_mmr: z.number().default(0),
  current_draft_last_pick_mmr: z.number().default(0),
});

DraftRoundSchema.extend({ draft: DraftSchema.nullable() });
