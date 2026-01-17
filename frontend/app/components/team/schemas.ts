import { z } from 'zod';
import { UserSchema } from '../user';

export const TeamSchema = z.object({
  name: z.string().min(1).max(100).nullable(),
  date: z.string().min(1).max(100).nullable(),
  members: z.array(UserSchema).nullable(),
  pk: z.number().min(0).nullable(),
  captain: UserSchema.nullable(),
  dropin_members: z.array(UserSchema).nullable(),
  left_members: z.array(UserSchema).nullable(),
  draft_order: z.number().nullable(),
  tournament: z.number().nullable(),
  current_points: z.number().nullable(),
  members_ids: z.array(z.number()).nullable(),
  dropin_member_ids: z.array(z.number()).nullable(),
  left_member_ids: z.array(z.number()).nullable(),
  captain_id: z.number().nullable(),
});
