import { z } from 'zod';
import type { UserType } from '~/components/user/types';

export const LeagueSchema = z.object({
  pk: z.number().optional(),
  organization: z.number(),
  organization_name: z.string().optional(),
  steam_league_id: z.number().min(1, 'Steam League ID is required'),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional().default(''),
  rules: z.string().optional().default(''),
  prize_pool: z.string().optional().default(''),
  admin_ids: z.array(z.number()).optional(),
  staff_ids: z.array(z.number()).optional(),
  tournament_count: z.number().optional(),
  last_synced: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export const CreateLeagueSchema = LeagueSchema.pick({
  organization: true,
  steam_league_id: true,
  name: true,
  description: true,
  rules: true,
});

export type LeagueType = z.infer<typeof LeagueSchema> & {
  admins?: UserType[];
  staff?: UserType[];
};
export type CreateLeagueInput = z.infer<typeof CreateLeagueSchema>;
export type LeaguesType = LeagueType[];
