import { z } from 'zod';

import { UserSchema } from '../user';

import { DraftSchema } from '../draft/schemas';
import { GameSchema } from '../game/schemas';
import { TeamSchema } from '../team';
import { STATE_CHOICES, TOURNAMENT_TYPE } from './constants';
export const TournamentSchema: z.ZodType<any> = z.object({
  name: z.string().nullable(),
  date_played: z.string().nullable(),
  users: z.array(UserSchema).nullable(),
  teams: z.array(TeamSchema).nullable(),
  captains: z.array(UserSchema).nullable(),
  captain_ids: z.array(z.number()).nullable(),
  pk: z.number().nullable(),
  winning_team: z.number().nullable(),
  state: z.enum(STATE_CHOICES).nullable(),
  tournament_type: z.enum(TOURNAMENT_TYPE).nullable(),
  games: z.array(GameSchema).nullable(),
  user_ids: z.array(z.number()).nullable(),
  team_ids: z.array(z.number()).nullable(),
  draft: DraftSchema.optional(),
});
