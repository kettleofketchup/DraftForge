import { z } from 'zod';

export const LeadershipProblemSchema = z.object({
  field: z.enum(['captain', 'deputy_captain']),
  code: z.enum([
    'captain_not_member',
    'deputy_not_member',
    'deputy_is_captain',
  ]),
  message: z.string(),
});
export type LeadershipProblem = z.infer<typeof LeadershipProblemSchema>;
