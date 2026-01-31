import { z } from 'zod';
import { TeamSchema } from '../team/schemas';
import { UserSchema } from '../user/schemas';

export const TeamDraftRoundSchema = z.object({
  pk: z.number().nullable(),
  draft: z.any(), // To be replaced with TeamDraftSchema
  captain: UserSchema.nullable(),
  pick_number: z.number().min(1).nullable(),
  pick_phase: z.number().min(1).nullable(),
  choice: UserSchema.nullable(),
  team: TeamSchema.nullable(),
});

// Use z.lazy() to avoid circular dependency with TournamentSchema
export const TeamDraftSchema = z.object({
  pk: z.number().nullable(),
  tournament: z.lazy(() => z.any()).nullable(), // Lazy reference to avoid circular import
  users_remaining: z.array(UserSchema).nullable(),
  draft_rounds: z.array(TeamDraftRoundSchema).nullable(),
  latest_round: z.number().nullable(),
  draft_style: z.enum(['snake', 'normal', 'shuffle']).default('snake'),
  snake_first_pick_mmr: z.number().default(0),
  snake_last_pick_mmr: z.number().default(0),
  normal_first_pick_mmr: z.number().default(0),
  normal_last_pick_mmr: z.number().default(0),
  current_draft_first_pick_mmr: z.number().default(0),
  current_draft_last_pick_mmr: z.number().default(0),
});

TeamDraftRoundSchema.extend({ draft: TeamDraftSchema.nullable() });

// Backwards compatibility aliases
export const DraftSchema = TeamDraftSchema;
export const DraftRoundSchema = TeamDraftRoundSchema;
