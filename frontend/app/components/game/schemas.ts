import { z } from 'zod';
import { TeamSchema } from '../team';
export const GameSchema = z.object({
  pk: z.number().nullable(),
  tournament: z.number().nullable(),
  round: z.number().nullable(),
  date_played: z.string().nullable(),
  radiant_team: TeamSchema.nullable(),
  radiant_team_id: z.number().nullable(),
  dire_team: TeamSchema.nullable(),
  dire_team_id: z.number().nullable(),
  winning_team: TeamSchema.nullable(),
  winning_team_id: z.number().nullable(),
  gameid: z.number().nullable(),
});
