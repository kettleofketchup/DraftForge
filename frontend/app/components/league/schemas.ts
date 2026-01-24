import { z } from 'zod';
import type { UserType } from '~/components/user/types';
import { UserSchema } from '~/components/user/schemas';
import {
  OrganizationSchema,
  type OrganizationType,
} from '~/components/organization/schemas';

// Lightweight org schema for league list view
const LeagueOrganizationSchema = z.object({
  pk: z.number(),
  name: z.string(),
  logo: z.string().optional(),
  league_count: z.number().optional(),
  created_at: z.string().optional(),
});

export const LeagueSchema = z.object({
  pk: z.number().optional(),
  organizations: z.array(LeagueOrganizationSchema).optional(),
  organization_ids: z.array(z.number()).optional(),
  organization_name: z.string().nullable().optional(), // Backwards compatibility
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

export const CreateLeagueSchema = z.object({
  organization_ids: z.array(z.number()).min(1, 'At least one organization is required'),
  steam_league_id: z.number().min(1, 'Steam League ID is required'),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().max(10000),
  rules: z.string().max(50000),
});

// Extended schema that includes nested user objects (returned by API)
export const LeagueWithUsersSchema = LeagueSchema.extend({
  admins: z.array(UserSchema).optional(),
  staff: z.array(UserSchema).optional(),
});

export type LeagueType = z.infer<typeof LeagueWithUsersSchema>;
export type CreateLeagueInput = z.infer<typeof CreateLeagueSchema>;
export type LeaguesType = LeagueType[];

// LeagueMatch schema - uses gameid to link to Steam matches
export const LeagueMatchSchema = z.object({
  pk: z.number(),
  tournament_pk: z.number().nullable(),
  tournament_name: z.string().nullable(),
  round: z.number().nullable(),
  date_played: z.string().nullable(),
  radiant_team: z.number().nullable(),
  dire_team: z.number().nullable(),
  radiant_team_name: z.string().nullable(),
  dire_team_name: z.string().nullable(),
  radiant_captain: UserSchema.nullable(),
  dire_captain: UserSchema.nullable(),
  winning_team: z.number().nullable(),
  gameid: z.number().nullable(),
});

export type LeagueMatchType = z.infer<typeof LeagueMatchSchema>;

// Edit league schema - consistent with CreateLeagueSchema validation
export const EditLeagueSchema = z.object({
  name: z.string().min(1, 'League name is required').max(255),
  description: z.string().max(10000),
  rules: z.string().max(50000),
  prize_pool: z.string().max(100),
});

export type EditLeagueInput = z.infer<typeof EditLeagueSchema>;
