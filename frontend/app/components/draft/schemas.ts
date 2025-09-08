import { z } from 'zod';
import { TeamSchema } from '../team/schemas';
import { TournamentSchema } from '../tournament/schemas';
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

export const DraftSchema = z.object({
  pk: z.number().nullable(),
  tournament: TournamentSchema.nullable(),
  users_remaining: z.array(UserSchema).nullable(),
  draft_rounds: z.array(DraftRoundSchema).nullable(),
  latest_round: z.number().nullable(),
});

DraftRoundSchema.extend({ draft: DraftSchema.nullable() });
