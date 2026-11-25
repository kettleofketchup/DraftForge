import { z } from 'zod';
import type { UserType } from '~/components/user/types';
import { TrackInfoSchema } from '~/features/standing/schemas';

export const OrganizationSchema = z.object({
  pk: z.number().optional(),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional().default(''),
  logo: z
    .union([z.string().url(), z.literal('')])
    .optional()
    .default(''),
  discord_link: z
    .union([z.string().url(), z.literal('')])
    .optional()
    .default(''),
  discord_server_id: z.string().max(20).nullable().optional(),
  rules_template: z.string().optional().default(''),
  timezone: z.string().optional().default('America/New_York'), // Default to US East
  members_private: z.boolean().optional().default(false),
  can_view_members: z.boolean().optional(), // per-viewer; absent means unknown
  members_viewer_pk: z.number().nullable().optional(),
  features: z.array(z.string()).optional().default([]),
  can_use_promotion: z.boolean().optional().default(false),
  can_manage_promotion_templates: z.boolean().optional().default(false),
  can_manage_promoters: z.boolean().optional().default(false),
  can_view_contributions: z.boolean().optional().default(false),
  can_view_contributors: z.boolean().optional().default(false),
  can_manage_contributions: z.boolean().optional().default(false),
  can_view_conduct: z.boolean().optional().default(false),
  can_view_own_conduct: z.boolean().optional().default(false),
  can_view_conduct_details: z.boolean().optional().default(false),
  can_manage_conduct: z.boolean().optional().default(false),
  standing_tracks: z.array(TrackInfoSchema).optional().default([]),
  owner_id: z.number().nullable().optional(),
  admin_ids: z.array(z.number()).optional(),
  staff_ids: z.array(z.number()).optional(),
  default_league: z.number().nullable().optional(),
  league_count: z.number().optional(),
  tournament_count: z.number().optional(),
  users_count: z.number().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export const CreateOrganizationSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string(),
  logo: z.union([z.string().url(), z.literal('')]),
  discord_link: z.union([z.string().url(), z.literal('')]),
  rules_template: z.string(),
});

export const EditOrganizationSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string(),
  logo: z.union([z.string().url(), z.literal('')]),
  discord_link: z.union([z.string().url(), z.literal('')]),
  discord_server_id: z.string().max(20).nullable().optional(),
  rules_template: z.string(),
  timezone: z.string().optional().default('America/New_York'),
  members_private: z.boolean().optional().default(false),
});

// Inferred types from Zod schemas
export type OrganizationType = z.infer<typeof OrganizationSchema> & {
  owner?: UserType | null;
  admins?: UserType[];
  staff?: UserType[];
};
export type CreateOrganizationInput = z.infer<typeof CreateOrganizationSchema>;
export type EditOrganizationInput = z.infer<typeof EditOrganizationSchema>;
export type OrganizationsType = OrganizationType[];

// backend/user/serializers.py PositionsSerializer
const OrgMemberPositionsSchema = z.object({
  pk: z.number(),
  carry: z.number(),
  mid: z.number(),
  offlane: z.number(),
  soft_support: z.number(),
  hard_support: z.number(),
});

// backend/org/serializers.py OrgUserSerializer, with include_game_mmrs=True
export const OrgMemberSchema = z.object({
  orgUserPk: z.number(),
  pk: z.number(),
  username: z.string().nullable(),
  nickname: z.string().nullable(),
  guildNickname: z.string().nullable(),
  discordNickname: z.string().nullable(),
  avatar: z.string().nullable(),
  discordId: z.string().nullable(),
  positions: OrgMemberPositionsSchema.nullable(),
  steam_account_id: z.number().nullable(),
  avatarUrl: z.string().nullable(),
  mmr: z.number(),
  mmr_game_type: z.number(),
  game_mmrs: z.record(z.string(), z.number()),
  league_mmr: z.number().nullable(),
});

export type OrgMemberType = z.infer<typeof OrgMemberSchema>;
